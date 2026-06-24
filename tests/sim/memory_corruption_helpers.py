from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

from dlcp_fw.paths import PROJECT_ROOT, V173_CONTROL_HEX, V35_MAIN_HEX
from dlcp_fw.sim.dlcp_sim_native import Chain


FILENAME_RAM_BASE = 0x02C0
FILENAME_LEN = 0x1E
PRESET_A_EEPROM_BASE = 0x60
PRESET_B_EEPROM_BASE = 0x83
MAIN_ACTIVE_FLAGS = 0x05E
MAIN_ACTIVE_PRESET_MASK = 0x04
EVENT_FLAGS = 0x07E
EVENT_DIRTY_SERVICE = 0x01
FILENAME_DIRTY_FLAGS = 0x0BD
FILENAME_DIRTY = 0x20
FILENAME_XACT_PENDING = 0x40
PRESET_JOB_STATE = 0x02DE
PRESET_JOB_TARGET = 0x02DF
PRESET_JOB_INDEX = 0x02E0
PRESET_JOB_DELAY = 0x02E1
PRESET_JOB_FLAGS = 0x02E2
PRESET_JOB_TBL_LO = 0x02E3
PRESET_JOB_TBL_HI = 0x02E4
PRESET_JOB_END = PRESET_JOB_TBL_HI
MAIN_SRC_ROUTE_REQUEST = 0x093
MAIN_RX_FRAME_POSITION = 0x098
MAIN_INPUT_SELECT = 0x099
MAIN_ROUTE_SHADOW = 0x0AB
MAIN_INPUT_SELECT_MIRROR = 0x0B3
MAIN_RX_RING_RD = 0x0C6
MAIN_RX_RING_WR = 0x0C7
MAIN_RX_RING_BASE = 0x0200
MAIN_RX_RING_SIZE = 0xC0
MAIN_RX_RING_END = MAIN_RX_RING_BASE + MAIN_RX_RING_SIZE - 1
MAIN_USB_EP1_OUT_BASE = 0x011A
MAIN_USB_EP1_OUT_END = 0x0159
MAIN_USB_EP1_IN_BASE = 0x015A
MAIN_USB_EP1_IN_END = 0x0199
MAIN_HID_STATE_BASE = 0x00B5
MAIN_HID_STATE_END = 0x00CE
MAIN_SETTINGS_EEPROM_FIRST = 0x00
MAIN_SETTINGS_EEPROM_LAST = 0x14
CONTROL_FLAGS = 0x01F
CONTROL_PRESET_EEPROM = 0x74
CONTROL_INPUT_INDEX = 0x0B7
CONTROL_INPUT_SELECT_CACHE = 0x0B8
CONTROL_VOLUME_CACHE = 0x0B9
CONTROL_DISPLAY_STATE_INDEX = 0x0BF
CONTROL_FNAME_CACHE = 0x0220
CONTROL_FNAME_LEN = 0x023E
CONTROL_FNAME_EXPECTED_LEN = 0x023F
CONTROL_FNAME_FLAGS = 0x0240
CONTROL_FNAME_ID = 0x0242
CONTROL_FNAME_SCROLL_OFF = 0x0243
CONTROL_FNAME_IDENTITY_GAP_FIRST = 0x0245
CONTROL_FNAME_IDENTITY_GAP_LAST = 0x0254
CONTROL_FNAME_DEADLINE_LO = 0x0257
CONTROL_FNAME_DEADLINE_HI = 0x0258
CONTROL_FNAME_RENDER_COL = 0x0259
CONTROL_FNAME_RENDER_OFF = 0x025A
CONTROL_FNAME_ROW0_STATUS = 0x025B
CONTROL_FNAME_TMP = 0x025C
CONTROL_FNAME_END = 0x025D
CONTROL_FNAME_RIGHT_GUARD = 0x025F
MAIN_V35_ASM = PROJECT_ROOT / "src/dlcp_fw/asm/dlcp_main_v35.asm"
MAIN_V35_LST = PROJECT_ROOT / "src/dlcp_fw/asm/dlcp_main_v35.lst"
CONTROL_V173_ASM = PROJECT_ROOT / "src/dlcp_fw/asm/dlcp_control_v173.asm"
CONTROL_V173_LST = PROJECT_ROOT / "src/dlcp_fw/asm/dlcp_control_v173.lst"

IR_ADDR_HYPEX = 0x10
IR_CMD_PRESET_A = 0x38
IR_CMD_PRESET_B = 0x39
IR_CMD_VOLUME_DOWN = 0x34


@dataclass(frozen=True)
class Stimulus:
    phase: str
    action: str
    params: dict[str, Any]
    tick_before: int
    tick_after: int


def trace_watch(
    *,
    role: str,
    space: str,
    start: int,
    end: int | None = None,
    label: str | None = None,
    protected: bool = False,
    stop_on_write: bool = False,
    fail_on_write: bool | None = None,
) -> dict[str, object]:
    """Build a native memory-trace watch with conservative defaults."""
    if end is None:
        end = start
    if fail_on_write is None:
        fail_on_write = protected
    return {
        "role": role,
        "space": space,
        "start": start,
        "end": end,
        "label": label or f"{role}.{space}.0x{start:03X}-0x{end:03X}",
        "protected": protected,
        "stop_on_write": stop_on_write,
        "fail_on_write": fail_on_write,
    }


def main_range_watches(
    start: int,
    end: int,
    label: str,
    *,
    units: tuple[int, ...] = (0, 1),
    space: str = "DataRam",
    protected: bool = False,
    fail_on_write: bool | None = None,
) -> list[dict[str, object]]:
    return [
        trace_watch(
            role=f"MAIN{unit}",
            space=space,
            start=start,
            end=end,
            label=f"MAIN{unit}.{label}",
            protected=protected,
            fail_on_write=fail_on_write,
        )
        for unit in units
    ]


def control_range_watch(
    start: int,
    end: int,
    label: str,
    *,
    space: str = "DataRam",
    protected: bool = False,
    fail_on_write: bool | None = None,
) -> dict[str, object]:
    return trace_watch(
        role="CONTROL",
        space=space,
        start=start,
        end=end,
        label=f"CONTROL.{label}",
        protected=protected,
        fail_on_write=fail_on_write,
    )


def slot(text: str) -> bytes:
    raw = text.encode("ascii")[:FILENAME_LEN]
    return raw + bytes([0xFF]) * (FILENAME_LEN - len(raw))


def start_v173_v35_chain() -> Chain:
    chain = Chain.from_v171_v32(
        control_hex_path=str(V173_CONTROL_HEX),
        main_hex_path=str(V35_MAIN_HEX),
    )
    assert chain.run_until_connected(limit=400) < 400
    chain.step_ticks(50_000_000)
    return chain


def start_v173_v35_single_main() -> Chain:
    chain = Chain.from_v17_v3x_chain(str(V173_CONTROL_HEX), str(V35_MAIN_HEX))
    assert chain.run_until_connected(limit=400) < 400
    chain.step_ticks(50_000_000)
    return chain


def start_v35_main_only() -> Chain:
    chain = Chain.from_v3x_main_only(str(V35_MAIN_HEX))
    chain.step_ticks(2_000_000_000)
    return chain


def read_eeprom_slot(chain: Chain, unit: int, base: int) -> bytes:
    return bytes(chain.read_main_eeprom_byte(unit, base + i) for i in range(FILENAME_LEN))


def read_filename_ram(chain: Chain, unit: int) -> bytes:
    return bytes(chain.read_main_reg(unit, FILENAME_RAM_BASE + i) for i in range(FILENAME_LEN))


def wait_filename_idle(chain: Chain, unit: int = 0, attempts: int = 30) -> None:
    for _ in range(attempts):
        if chain.read_main_reg(unit, FILENAME_DIRTY_FLAGS) == 0:
            return
        chain.write_main_reg(
            unit,
            EVENT_FLAGS,
            chain.read_main_reg(unit, EVENT_FLAGS) | EVENT_DIRTY_SERVICE,
        )
        chain.step_ticks(5_000_000)
    raise AssertionError(
        f"MAIN{unit} filename dirty flags did not clear: "
        f"0x{chain.read_main_reg(unit, FILENAME_DIRTY_FLAGS):02X}"
    )


def set_active_preset(chain: Chain, unit: int, preset_b: bool) -> None:
    flags = chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS)
    if preset_b:
        flags |= MAIN_ACTIVE_PRESET_MASK
    else:
        flags &= ~MAIN_ACTIVE_PRESET_MASK
    chain.write_main_reg(unit, MAIN_ACTIVE_FLAGS, flags)


def stage_filename_ram(chain: Chain, unit: int, payload: bytes) -> None:
    assert len(payload) == FILENAME_LEN
    for offset, value in enumerate(payload):
        chain.write_main_reg(unit, FILENAME_RAM_BASE + offset, value)
    assert read_filename_ram(chain, unit) == payload


def persist_filename_firmware_path(
    chain: Chain,
    unit: int,
    payload: bytes,
    *,
    preset_b: bool,
) -> None:
    wait_filename_idle(chain, unit)
    set_active_preset(chain, unit, preset_b)
    stage_filename_ram(chain, unit, payload)
    chain.write_main_reg(unit, FILENAME_DIRTY_FLAGS, FILENAME_DIRTY | FILENAME_XACT_PENDING)
    chain.write_main_reg(
        unit,
        EVENT_FLAGS,
        chain.read_main_reg(unit, EVENT_FLAGS) | EVENT_DIRTY_SERVICE,
    )
    for _ in range(40):
        chain.step_ticks(5_000_000)
        if chain.read_main_reg(unit, FILENAME_DIRTY_FLAGS) == 0:
            break
    assert chain.read_main_reg(unit, FILENAME_DIRTY_FLAGS) == 0
    # Dirty-service completion and EEPROM-cell commit are decoupled in the
    # simulator just like silicon: WR completion is delayed after the arm.
    # Drain that tail before a protected post-repair trace is enabled.
    chain.step_ticks(20_000_000)
    expected_base = PRESET_B_EEPROM_BASE if preset_b else PRESET_A_EEPROM_BASE
    assert read_eeprom_slot(chain, unit, expected_base) == payload


def firmware_path_repair_all_filename_slots(
    chain: Chain,
    slot_a: bytes,
    slot_b: bytes,
    units: tuple[int, ...] = (0, 1),
) -> None:
    for unit in units:
        persist_filename_firmware_path(chain, unit, slot_a, preset_b=False)
        persist_filename_firmware_path(chain, unit, slot_b, preset_b=True)


def main_filename_eeprom_watches(
    *,
    slots: tuple[str, ...] = ("a", "b"),
    units: tuple[int, ...] = (0, 1),
    protected: bool = True,
) -> list[dict[str, object]]:
    watches: list[dict[str, object]] = []
    for slot_name in slots:
        if slot_name == "a":
            base = PRESET_A_EEPROM_BASE
        elif slot_name == "b":
            base = PRESET_B_EEPROM_BASE
        else:
            raise ValueError(f"unknown filename slot {slot_name!r}")
        watches.extend(
            main_range_watches(
                base,
                base + FILENAME_LEN - 1,
                f"preset_{slot_name}_filename_eeprom",
                units=units,
                space="Eeprom",
                protected=protected,
            )
        )
    return watches


def main_filename_ram_watches(
    *,
    units: tuple[int, ...] = (0, 1),
    protected: bool = False,
) -> list[dict[str, object]]:
    return main_range_watches(
        FILENAME_RAM_BASE,
        FILENAME_RAM_BASE + FILENAME_LEN - 1,
        "filename_ram",
        units=units,
        protected=protected,
    )


def main_preset_job_watches(
    *,
    units: tuple[int, ...] = (0, 1),
    protected: bool = False,
) -> list[dict[str, object]]:
    return main_range_watches(
        PRESET_JOB_STATE,
        PRESET_JOB_END,
        "preset_job_block",
        units=units,
        protected=protected,
    )


def main_rx_ring_watches(
    *,
    units: tuple[int, ...] = (0, 1),
    protected: bool = False,
) -> list[dict[str, object]]:
    watches = main_range_watches(
        MAIN_RX_RING_BASE,
        MAIN_RX_RING_END,
        "rx_ring_buffer",
        units=units,
        protected=protected,
    )
    watches.extend(
        main_range_watches(
            MAIN_RX_RING_RD,
            MAIN_RX_RING_WR,
            "rx_ring_indices",
            units=units,
            protected=protected,
        )
    )
    watches.extend(
        main_range_watches(
            MAIN_RX_FRAME_POSITION,
            MAIN_RX_FRAME_POSITION,
            "rx_frame_position",
            units=units,
            protected=protected,
        )
    )
    return watches


def main_route_state_watches(
    *,
    units: tuple[int, ...] = (0, 1),
    protected: bool = False,
) -> list[dict[str, object]]:
    watches: list[dict[str, object]] = []
    for addr, label in (
        (MAIN_SRC_ROUTE_REQUEST, "src_route_request"),
        (MAIN_INPUT_SELECT, "input_select"),
        (MAIN_ROUTE_SHADOW, "route_shadow"),
        (MAIN_INPUT_SELECT_MIRROR, "input_select_mirror"),
    ):
        watches.extend(
            main_range_watches(addr, addr, label, units=units, protected=protected)
        )
    return watches


def control_preset_eeprom_watches() -> list[dict[str, object]]:
    return [
        control_range_watch(
            CONTROL_PRESET_EEPROM - 4,
            CONTROL_PRESET_EEPROM - 1,
            "preset_eeprom_left_guard",
            space="Eeprom",
            protected=True,
        ),
        control_range_watch(
            CONTROL_PRESET_EEPROM,
            CONTROL_PRESET_EEPROM,
            "preset_eeprom",
            space="Eeprom",
        ),
        control_range_watch(
            CONTROL_PRESET_EEPROM + 1,
            CONTROL_PRESET_EEPROM + 4,
            "preset_eeprom_right_guard",
            space="Eeprom",
            protected=True,
        ),
    ]


def control_filename_cache_watches() -> list[dict[str, object]]:
    return [
        control_range_watch(0x021C, 0x021F, "fname_left_guard", protected=True),
        control_range_watch(CONTROL_FNAME_CACHE, CONTROL_FNAME_END, "fname_cache"),
        control_range_watch(
            CONTROL_FNAME_IDENTITY_GAP_FIRST,
            CONTROL_FNAME_IDENTITY_GAP_LAST,
            "fname_identity_gap",
            protected=True,
        ),
        control_range_watch(
            CONTROL_FNAME_RIGHT_GUARD,
            CONTROL_FNAME_RIGHT_GUARD,
            "fname_right_guard",
            protected=True,
        ),
    ]


def protected_filename_watches() -> list[dict[str, object]]:
    watches: list[dict[str, object]] = []
    for unit in (0, 1):
        role = f"MAIN{unit}"
        watches.extend(
            [
                trace_watch(
                    role=role,
                    space="Eeprom",
                    start=PRESET_B_EEPROM_BASE,
                    end=PRESET_B_EEPROM_BASE + FILENAME_LEN - 1,
                    label=f"{role}.preset_b_filename_eeprom",
                    protected=True,
                ),
                trace_watch(
                    role=role,
                    space="DataRam",
                    start=FILENAME_RAM_BASE,
                    end=FILENAME_RAM_BASE + FILENAME_LEN - 1,
                    label=f"{role}.filename_ram",
                ),
                trace_watch(
                    role=role,
                    space="DataRam",
                    start=MAIN_ACTIVE_FLAGS,
                    label=f"{role}.active_flags",
                ),
                trace_watch(
                    role=role,
                    space="DataRam",
                    start=EVENT_FLAGS,
                    label=f"{role}.event_flags",
                ),
                trace_watch(
                    role=role,
                    space="DataRam",
                    start=FILENAME_DIRTY_FLAGS,
                    label=f"{role}.filename_dirty_flags",
                ),
                trace_watch(
                    role=role,
                    space="DataRam",
                    start=PRESET_JOB_STATE,
                    label=f"{role}.preset_job_state",
                ),
                trace_watch(
                    role=role,
                    space="DataRam",
                    start=PRESET_JOB_TARGET,
                    label=f"{role}.preset_job_target",
                ),
            ]
        )
    return watches


def single_byte_eeprom_watch(
    *,
    role: str = "MAIN0",
    addr: int = PRESET_B_EEPROM_BASE + 0x0C,
    protected: bool = False,
) -> list[dict[str, object]]:
    return [
        {
            "role": role,
            "space": "Eeprom",
            "start": addr,
            "end": addr,
            "label": f"{role}.eeprom_0x{addr:02X}",
            "protected": protected,
            "fail_on_write": protected,
        }
    ]


def assert_trace_clean(chain: Chain) -> None:
    summary = chain.memory_trace_summary()
    assert not summary["overflowed"], summary
    assert summary["dropped_count"] == 0, summary
    assert chain.memory_trace_first_violation() is None


def wait_preset_jobs_idle(chain: Chain, *, units: tuple[int, ...] = (0, 1)) -> None:
    for _ in range(80):
        if all(chain.read_main_reg(unit, PRESET_JOB_STATE) == 0 for unit in units):
            return
        chain.step_ticks(5_000_000)
    states = {
        unit: {
            "state": chain.read_main_reg(unit, PRESET_JOB_STATE),
            "target": chain.read_main_reg(unit, PRESET_JOB_TARGET),
            "index": chain.read_main_reg(unit, PRESET_JOB_INDEX),
        }
        for unit in units
    }
    raise AssertionError(f"preset jobs did not become idle: {states!r}")


def run_preset_toggle_churn(chain: Chain) -> list[Stimulus]:
    stimuli: list[Stimulus] = []

    def record(phase: str, action: str, params: dict[str, Any], fn) -> None:  # type: ignore[no-untyped-def]
        before = chain.current_tick()
        fn()
        after = chain.current_tick()
        stimuli.append(Stimulus(phase, action, params, before, after))

    for cmd in (IR_CMD_PRESET_B, IR_CMD_PRESET_A, IR_CMD_PRESET_B, IR_CMD_PRESET_A):
        record(
            "preset",
            "ir",
            {"addr": IR_ADDR_HYPEX, "cmd": cmd},
            lambda cmd=cmd: (
                chain.inject_decoded_ir_event(addr=IR_ADDR_HYPEX, cmd=cmd),
                chain.step_ticks(80_000_000),
            ),
        )
    wait_preset_jobs_idle(chain)
    return stimuli


def run_main_route_churn(chain: Chain, *, units: tuple[int, ...] = (0, 1)) -> list[Stimulus]:
    stimuli: list[Stimulus] = []

    def record(phase: str, action: str, params: dict[str, Any], fn) -> None:  # type: ignore[no-untyped-def]
        before = chain.current_tick()
        fn()
        after = chain.current_tick()
        stimuli.append(Stimulus(phase, action, params, before, after))

    for data in (0x00, 0x05, 0x08, 0x01, 0x06, 0x07):
        for unit in units:
            record(
                "route",
                "inject_main_uart_rx_bytes",
                {"unit": unit, "frame": [0xB0, 0x06, data]},
                lambda unit=unit, data=data: chain.inject_main_uart_rx_bytes(
                    unit, [0xB0, 0x06, data]
                ),
            )
        record("route", "settle", {"ticks": 12_000_000}, lambda: chain.step_ticks(12_000_000))
    return stimuli


def run_usb_hid_readonly_churn(chain: Chain, *, unit: int = 0) -> list[Stimulus]:
    stimuli: list[Stimulus] = []

    def record(phase: str, action: str, params: dict[str, Any], fn) -> None:  # type: ignore[no-untyped-def]
        before = chain.current_tick()
        fn()
        after = chain.current_tick()
        stimuli.append(Stimulus(phase, action, params, before, after))

    reports = [
        bytes([0x43, 0x00, 0x00, 0x00] + [0x00] * 60),
        bytes([0x44] + [0x00] * 63),
        bytes([0x45, 0x13] + [0x00] * 62),
        bytes([0x45, 0x32, 0x03, 0xA5] + [0x00] * 60),
        bytes([0x46] + [0x00] * 63),
    ]
    for report in reports:
        record(
            "usb",
            "firmware_hid_report",
            {"unit": unit, "opcode": report[0], "arg": report[1] if len(report) > 1 else 0},
            lambda report=report: chain.firmware_hid_report(unit, report, max_steps=120_000),
        )
        record("usb", "settle", {"ticks": 2_000_000}, lambda: chain.step_ticks(2_000_000))
    return stimuli


def run_live_like_churn(chain: Chain) -> list[Stimulus]:
    stimuli: list[Stimulus] = []

    def record(phase: str, action: str, params: dict[str, Any], fn) -> None:  # type: ignore[no-untyped-def]
        before = chain.current_tick()
        fn()
        after = chain.current_tick()
        stimuli.append(Stimulus(phase, action, params, before, after))

    record("idle", "step_ticks", {"ticks": 48_000_000}, lambda: chain.step_ticks(48_000_000))
    query_tx_mark = len(chain.uart_tx_records_full())
    query_rx_mark = len(chain.uart_rx_records_full())
    record(
        "preset-query",
        "inject_main_frames_fifo",
        {"frames": [[0xB1, 0x26, 0x01]], "fifo_limit": 47},
        lambda: chain.inject_main_frames_fifo([[0xB1, 0x26, 0x01]], fifo_limit=47),
    )
    record(
        "preset-query",
        "settle",
        {"ticks": 120_000_000},
        lambda: chain.step_ticks(120_000_000),
    )
    query_tx = chain.uart_tx_records_full()[query_tx_mark:]
    query_rx = chain.uart_rx_records_full()[query_rx_mark:]
    query_tx_bytes = [byte for _tick, _src, _dst, byte in query_tx]
    query_rx_bytes = [byte for _tick, _src, _dst, byte in query_rx]
    query_pairs = sorted(
        {
            f"{query_tx_bytes[idx]:02X}/{query_tx_bytes[idx + 1]:02X}"
            for idx in range(len(query_tx_bytes) - 1)
            if query_tx_bytes[idx] == 0xBF
        }
    )
    now = chain.current_tick()
    stimuli.append(
        Stimulus(
            "preset-query",
            "observe_uart",
            {
                "injected_query": [0xB1, 0x26, 0x01],
                "tx_pairs_after_query": query_pairs,
                "rx_bytes_after_query_head": query_rx_bytes[:64],
            },
            now,
            now,
        )
    )
    record(
        "preset",
        "ir_preset_b",
        {"addr": IR_ADDR_HYPEX, "cmd": IR_CMD_PRESET_B},
        lambda: (chain.inject_decoded_ir_event(addr=IR_ADDR_HYPEX, cmd=IR_CMD_PRESET_B), chain.step_ticks(80_000_000)),
    )
    record(
        "volume",
        "ir_volume_down",
        {"addr": IR_ADDR_HYPEX, "cmd": IR_CMD_VOLUME_DOWN},
        lambda: (chain.inject_decoded_ir_event(addr=IR_ADDR_HYPEX, cmd=IR_CMD_VOLUME_DOWN), chain.step_ticks(20_000_000)),
    )
    for key in ("RIGHT", "RIGHT", "LEFT", "RIGHT", "LEFT", "UP", "DOWN"):
        record("menu", "press", {"key": key}, lambda key=key: chain.press(key))
        record("menu", "settle", {"ticks": 8_000_000}, lambda: chain.step_ticks(8_000_000))
    record(
        "preset",
        "ir_preset_a",
        {"addr": IR_ADDR_HYPEX, "cmd": IR_CMD_PRESET_A},
        lambda: (chain.inject_decoded_ir_event(addr=IR_ADDR_HYPEX, cmd=IR_CMD_PRESET_A), chain.step_ticks(80_000_000)),
    )
    record("power", "por", {"source": "por"}, lambda: chain.apply_reset_all("por"))
    record("power", "reconnect", {"limit": 400}, lambda: chain.run_until_connected(limit=400))
    record("idle", "post_reconnect_idle", {"ticks": 50_000_000}, lambda: chain.step_ticks(50_000_000))
    return stimuli


def run_direct_main_rx_stimulus(chain: Chain, unit: int = 0) -> list[Stimulus]:
    stimuli: list[Stimulus] = []

    def record(phase: str, action: str, params: dict[str, Any], fn) -> None:  # type: ignore[no-untyped-def]
        before = chain.current_tick()
        fn()
        after = chain.current_tick()
        stimuli.append(Stimulus(phase, action, params, before, after))

    for frame in ([0xB0, 0x20, 0x00], [0xB0, 0x20, 0x01], [0xB1, 0x26, 0x00]):
        record(
            "direct-main-rx",
            "inject_main_uart_rx_bytes",
            {"unit": unit, "bytes": frame},
            lambda frame=frame: chain.inject_main_uart_rx_bytes(unit, frame),
        )
        record("direct-main-rx", "settle", {"ticks": 20_000_000}, lambda: chain.step_ticks(20_000_000))
    for raw in ([0x00], [0xFF], [0xB1, 0x26], [0xB0, 0x20, 0x00, 0xB1, 0x26, 0x01]):
        record(
            "direct-main-rx",
            "inject_raw_uart_bytes",
            {"unit": unit, "bytes": raw},
            lambda raw=raw: chain.inject_main_uart_rx_bytes(unit, raw),
        )
        record("direct-main-rx", "settle", {"ticks": 10_000_000}, lambda: chain.step_ticks(10_000_000))
    return stimuli


def final_state(chain: Chain) -> dict[str, Any]:
    return {
        "tick": chain.current_tick(),
        "lcd": list(chain.lcd_lines()),
        "mains": [
            {
                "unit": unit,
                "active_flags": chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS),
                "event_flags": chain.read_main_reg(unit, EVENT_FLAGS),
                "filename_dirty_flags": chain.read_main_reg(unit, FILENAME_DIRTY_FLAGS),
                "preset_job_state": chain.read_main_reg(unit, PRESET_JOB_STATE),
                "preset_job_target": chain.read_main_reg(unit, PRESET_JOB_TARGET),
                "filename_ram_hex": read_filename_ram(chain, unit).hex(),
                "preset_a_hex": read_eeprom_slot(chain, unit, PRESET_A_EEPROM_BASE).hex(),
                "preset_b_hex": read_eeprom_slot(chain, unit, PRESET_B_EEPROM_BASE).hex(),
            }
            for unit in (0, 1)
        ],
    }


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_status_short() -> list[str]:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return [f"<git status failed: {result.stderr.strip()}>"]
    return result.stdout.splitlines()


def _file_entry(path: Path) -> dict[str, str | None]:
    return {"path": str(path), "sha256": _sha256_file(path)}


def _listing_index(listing_path: Path) -> tuple[dict[int, dict[str, Any]], list[tuple[int, str]]]:
    lines: dict[int, dict[str, Any]] = {}
    symbols: list[tuple[int, str]] = []
    if not listing_path.exists():
        return lines, symbols
    symbol_re = re.compile(r"^(\S+)\s+ADDRESS\s+([0-9A-Fa-f]{8})\s+\d+")
    for line_no, line in enumerate(listing_path.read_text(errors="replace").splitlines(), 1):
        match = symbol_re.match(line)
        if match:
            symbols.append((int(match.group(2), 16), match.group(1)))
            continue
        parts = line.split()
        if not parts:
            continue
        loc = parts[0]
        if len(loc) != 6 or not all(ch in "0123456789abcdefABCDEF" for ch in loc):
            continue
        addr = int(loc, 16)
        idx = 1
        object_words: list[str] = []
        while idx < len(parts):
            token = parts[idx]
            if len(token) == 4 and all(ch in "0123456789abcdefABCDEF" for ch in token):
                object_words.append(token)
                idx += 1
                continue
            break
        source_line = None
        source_text = ""
        if idx < len(parts):
            if parts[idx].isdigit():
                source_line = int(parts[idx])
                source_text = " ".join(parts[idx + 1 :])
            else:
                source_text = " ".join(parts[idx:])
        mnemonic = source_text.strip().split(None, 1)[0] if source_text.strip() else ""
        access_mode = None
        if "ACCESS" in source_text:
            access_mode = "ACCESS"
        elif "BANKED" in source_text:
            access_mode = "BANKED"
        lines[addr] = {
            "listing_path": str(listing_path),
            "listing_line": line_no,
            "asm_source_line": source_line,
            "opcode_words": object_words,
            "source": source_text,
            "mnemonic": mnemonic,
            "access_mode": access_mode,
        }
    symbols.sort()
    return lines, symbols


def _nearest_symbol(symbols: list[tuple[int, str]], pc: int) -> tuple[str | None, int | None]:
    best_addr: int | None = None
    best_name: str | None = None
    for addr, name in symbols:
        if addr > pc:
            break
        best_addr = addr
        best_name = name
    if best_addr is None:
        return None, None
    return best_name, pc - best_addr


def _source_map_for_record(
    record: dict[str, Any],
    main_index: tuple[dict[int, dict[str, Any]], list[tuple[int, str]]],
    control_index: tuple[dict[int, dict[str, Any]], list[tuple[int, str]]],
) -> dict[str, Any] | None:
    pc = record.get("pc")
    if pc is None:
        return None
    role = str(record.get("role", ""))
    if role.startswith("MAIN"):
        asm_path = MAIN_V35_ASM
        listing_path = MAIN_V35_LST
        lines, symbols = main_index
    elif role == "CONTROL":
        asm_path = CONTROL_V173_ASM
        listing_path = CONTROL_V173_LST
        lines, symbols = control_index
    else:
        return None
    pc_int = int(pc)
    line = lines.get(pc_int, {})
    symbol, offset = _nearest_symbol(symbols, pc_int)
    return {
        "asm_path": str(asm_path),
        "listing_path": str(listing_path),
        "listing_line": line.get("listing_line"),
        "asm_source_line": line.get("asm_source_line"),
        "nearest_symbol": symbol,
        "symbol_offset": offset,
        "opcode_words": line.get("opcode_words", []),
        "mnemonic": line.get("mnemonic", ""),
        "source": line.get("source", ""),
        "access_mode": line.get("access_mode"),
        "effective_addr": record.get("addr"),
    }


def _enriched_trace_records(chain: Chain) -> list[dict[str, Any]]:
    main_index = _listing_index(MAIN_V35_LST)
    control_index = _listing_index(CONTROL_V173_LST)
    enriched = []
    for record in chain.memory_trace_records():
        item = dict(record)
        item["source_map"] = _source_map_for_record(item, main_index, control_index)
        enriched.append(item)
    return enriched


def write_trace_artifacts(
    out_root: Path,
    scenario: str,
    seed: int,
    chain: Chain,
    stimuli: list[Stimulus],
    watches: list[dict[str, object]] | None = None,
    rerun_command: list[str] | None = None,
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = out_root / f"{timestamp}_{scenario}_{seed:08x}"
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_summary = chain.memory_trace_summary()
    manifest = {
        "scenario": scenario,
        "seed": seed,
        "argv": rerun_command or [],
        "rerun_command": " ".join(rerun_command or []),
        "git_status_short": _git_status_short(),
        "firmware": {
            "control_hex": _file_entry(V173_CONTROL_HEX),
            "main_hex": _file_entry(V35_MAIN_HEX),
        },
        "source": {
            "control_asm": _file_entry(CONTROL_V173_ASM),
            "control_listing": _file_entry(CONTROL_V173_LST),
            "main_asm": _file_entry(MAIN_V35_ASM),
            "main_listing": _file_entry(MAIN_V35_LST),
        },
        "topology": {
            "factory": "V1.73 CONTROL + V3.5 MAIN chain",
            "roles": ["CONTROL", "MAIN0", "MAIN1"],
            "main0_distinct_from_main1": True,
        },
        "watch_config": watches or protected_filename_watches(),
        "trace_summary": trace_summary,
        "final_main_state": final_state(chain)["mains"],
        "live_probe_anchors": [
            "artifacts/probes/live_filename_eeprom_surgery_20260621.json",
            "artifacts/probes/live_filename_eeprom_left_b_repair2_20260621.json",
            "artifacts/probes/live_filename_eeprom_post_powercycle_check_20260621.json",
        ],
    }
    (out_dir / "metadata.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with (out_dir / "stimuli.jsonl").open("w") as fh:
        for stimulus in stimuli:
            fh.write(json.dumps(stimulus.__dict__, sort_keys=True) + "\n")
    with (out_dir / "stimulus.jsonl").open("w") as fh:
        for stimulus in stimuli:
            fh.write(json.dumps(stimulus.__dict__, sort_keys=True) + "\n")
    with (out_dir / "trace.jsonl").open("w") as fh:
        for record in _enriched_trace_records(chain):
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    with (out_dir / "uart_tx_records.jsonl").open("w") as fh:
        for tick, src, dst, byte in chain.uart_tx_records_full():
            fh.write(json.dumps({"tick": tick, "src": src, "dst": dst, "byte": byte}) + "\n")
    with (out_dir / "uart_rx_records.jsonl").open("w") as fh:
        for tick, src, dst, byte in chain.uart_rx_records_full():
            fh.write(json.dumps({"tick": tick, "src": src, "dst": dst, "byte": byte}) + "\n")
    (out_dir / "final_state.json").write_text(json.dumps(final_state(chain), indent=2) + "\n")
    live_probe_paths = [
        PROJECT_ROOT / "artifacts/probes/live_filename_eeprom_surgery_20260621.json",
        PROJECT_ROOT / "artifacts/probes/live_filename_eeprom_left_b_repair2_20260621.json",
        PROJECT_ROOT / "artifacts/probes/live_filename_eeprom_post_powercycle_check_20260621.json",
    ]
    (out_dir / "live_evidence.json").write_text(
        json.dumps(
            {
                "expected_preset_b": "LX521.4 22MG10F-v7",
                "observed_symptom": "LX521.4 22MG\\x000F-v7",
                "affected_addr": "0x8F",
                "affected_expected": "0x31",
                "affected_observed": "0x00",
                "probe_artifacts": [_file_entry(path) for path in live_probe_paths],
            },
            indent=2,
        )
        + "\n"
    )
    first = trace_summary.get("first_violation")
    (out_dir / "summary.md").write_text(
        "# Memory Corruption Summary\n\n"
        f"- Scenario: `{scenario}`\n"
        f"- Trace records: `{trace_summary.get('record_count')}` "
        f"(total `{trace_summary.get('total_count')}`, dropped `{trace_summary.get('dropped_count')}`)\n"
        f"- First violation: `{json.dumps(first, sort_keys=True) if first else 'none'}`\n"
    )
    (out_dir / "README.md").write_text(
        "# Memory Corruption Trace\n\n"
        "Generated by tests/sim/memory_corruption_helpers.py. "
        "Trace records are range-triggered memory writes with role, PC, "
        "CPU snapshot, and EEPROM arm metadata when available.\n"
    )
    return out_dir


def _format_guard_failure(
    violation: dict[str, Any] | None,
    artifact_dir: Path,
    summary: dict[str, Any],
) -> str:
    if violation is None:
        return (
            "MEMTRACE_GUARD failed: protected evidence was lost "
            f"artifact={artifact_dir} dropped={summary.get('dropped_count')} "
            f"overflowed={summary.get('overflowed')}"
        )

    arm = violation.get("arm") or {}
    pc = violation.get("pc")
    pc_text = "n/a" if pc is None else f"0x{int(pc):04X}"
    return (
        "MEMTRACE_GUARD failed: "
        f"{violation.get('role')} {violation.get('space')}["
        f"0x{int(violation.get('addr', 0)):02X} {violation.get('label')}] "
        f"0x{int(violation.get('old', 0)):02X}->0x{int(violation.get('new', 0)):02X} "
        f"kind={violation.get('kind')} record={violation.get('seq')} "
        f"tick={violation.get('tick')} armed_by_pc={pc_text} "
        f"eeadr=0x{int(arm.get('eeadr', violation.get('addr', 0))):02X} "
        f"eedata=0x{int(arm.get('eedata', violation.get('new', 0))):02X} "
        f"artifact={artifact_dir} dropped={summary.get('dropped_count')} "
        f"overflowed={summary.get('overflowed')}"
    )


def assert_no_protected_memory_writes(
    chain: Chain,
    scenario_fn: Callable[[Chain], list[Stimulus]],
    *,
    watches: list[dict[str, object]] | None = None,
    scenario: str,
    seed: int = 0,
    out_root: Path | None = None,
    max_records: int = 10_000,
    rerun_command: list[str] | None = None,
) -> list[Stimulus]:
    """Run a scenario under protected memtrace and fail with artifacts.

    Call this only after test setup has completed and any legitimate firmware
    writes have drained.  The helper clears any previous trace, starts the
    supplied protected watches, runs ``scenario_fn``, writes a replay artifact,
    and fails if a protected write occurs or if trace evidence is dropped.
    """
    watch_config = watches or protected_filename_watches()
    chain.clear_memory_trace()
    chain.begin_memory_trace(watch_config, max_records=max_records)
    stimuli = scenario_fn(chain)
    out_dir = write_trace_artifacts(
        out_root or (PROJECT_ROOT / "artifacts/reanalysis/memory_corruption"),
        scenario,
        seed,
        chain,
        stimuli,
        watches=watch_config,
        rerun_command=rerun_command,
    )
    summary = chain.memory_trace_summary()
    violation = chain.memory_trace_first_violation()
    if summary.get("overflowed") or summary.get("dropped_count") or violation is not None:
        raise AssertionError(_format_guard_failure(violation, out_dir, summary))
    return stimuli
