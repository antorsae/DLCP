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


def protected_filename_watches() -> list[dict[str, object]]:
    watches: list[dict[str, object]] = []
    for unit in (0, 1):
        role = f"MAIN{unit}"
        watches.extend(
            [
                {
                    "role": role,
                    "space": "Eeprom",
                    "start": PRESET_B_EEPROM_BASE,
                    "end": PRESET_B_EEPROM_BASE + FILENAME_LEN - 1,
                    "label": f"{role}.preset_b_filename_eeprom",
                    "protected": True,
                    "fail_on_write": True,
                },
                {
                    "role": role,
                    "space": "DataRam",
                    "start": FILENAME_RAM_BASE,
                    "end": FILENAME_RAM_BASE + FILENAME_LEN - 1,
                    "label": f"{role}.filename_ram",
                },
                {
                    "role": role,
                    "space": "DataRam",
                    "start": MAIN_ACTIVE_FLAGS,
                    "end": MAIN_ACTIVE_FLAGS,
                    "label": f"{role}.active_flags",
                },
                {
                    "role": role,
                    "space": "DataRam",
                    "start": EVENT_FLAGS,
                    "end": EVENT_FLAGS,
                    "label": f"{role}.event_flags",
                },
                {
                    "role": role,
                    "space": "DataRam",
                    "start": FILENAME_DIRTY_FLAGS,
                    "end": FILENAME_DIRTY_FLAGS,
                    "label": f"{role}.filename_dirty_flags",
                },
                {
                    "role": role,
                    "space": "DataRam",
                    "start": PRESET_JOB_STATE,
                    "end": PRESET_JOB_STATE,
                    "label": f"{role}.preset_job_state",
                },
                {
                    "role": role,
                    "space": "DataRam",
                    "start": PRESET_JOB_TARGET,
                    "end": PRESET_JOB_TARGET,
                    "label": f"{role}.preset_job_target",
                },
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
