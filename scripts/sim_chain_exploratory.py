#!/usr/bin/env python3
"""Exploratory DLCP chain simulator campaign runner.

This is intentionally not a pytest wrapper.  It generates new, seeded
chain-session combinations from docs/SIM_CHAIN_EXPLORATORY_STRESS_SPEC.md and
records enough evidence to replay/minimize interesting outcomes later.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import secrets
import sys
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from dlcp_fw.paths import PROJECT_ROOT, SIM_ARTIFACTS_DIR, V173_CONTROL_HEX, V34_MAIN_HEX
from dlcp_fw.sim.dlcp_sim_native import Chain


DISPLAY_STATE_INDEX = 0x0BF
CONTROL_FLAGS = 0x01F
CONTROL_CONNECTED_MASK = 0x02
CONTROL_MUTE_MASK = 0x20
CONTROL_PRESET_B_MASK = 0x40
VOLUME_CACHE = 0x0B9
INPUT_CACHE = 0x0B8

IR_ADDR_HYPEX = 0x10
IR_PROFILE_ADDR = 0x020
IR_PROFILE_POWER = 0x021
IR_PROFILE_VOL_UP = 0x022
IR_PROFILE_VOL_DOWN = 0x023
IR_PROFILE_INPUT_UP = 0x024
IR_PROFILE_INPUT_DOWN = 0x025
IR_PROFILE_MUTE = 0x026
# Real profile-0x04 (Hypex remote, addr 0x10) command codes the V1.73 firmware
# actually loads into ir_cmd_cfg (0x021..0x026) at boot — verified empirically.
# Previously the harness wrote a synthetic Frankenstein map (addr 0x10 + standard
# RC-5 codes 0x0C/0x10/0x11/0x20/0x21/0x0D), which masked any profile-load bug.
# Using the firmware's real codes against its own un-clobbered map means a broken
# profile load now surfaces as a configurable IR command that fails to dispatch.
IR_CMDS = {
    "power": 0x32,
    "mute": 0x35,
    "volume_up": 0x33,
    "volume_down": 0x34,
    "input_up": 0x36,
    "input_down": 0x37,
    "preset_a": 0x38,   # V1.71 hardcoded inline shortcut (profile-independent)
    "preset_b": 0x39,   # V1.71 hardcoded inline shortcut (profile-independent)
    "standby": 0x3A,    # V1.71 hardcoded inline shortcut (profile-independent)
    "wake": 0x3B,       # V1.71 hardcoded inline shortcut (profile-independent)
}
CONTROL_IR_PROFILE_SEL = 0x0A7  # cmd1d_setting: 0x04=Hypex@0x10, 0x03=RC-5@0x00

MAIN_ACTIVE_FLAGS = 0x05E
MAIN_ACTIVE_PRESET_MASK = 0x04
MAIN_ACTIVE_GATE_MASK = 0x08
MAIN_PRESET_JOB_STATE = 0x2DE
MAIN_PRESET_JOB_TARGET = 0x2DF
# Semantically-critical MAIN state the oracle was previously blind to.  Without
# these, mute-leak (Class 5) and IR/volume/route bugs cannot be distinguished
# from benign refresh traffic.  Addresses from src/dlcp_fw/asm/dlcp_main_ram.inc.
MAIN_LOGICAL_VOLUME = 0x066
MAIN_COMPUTED_VOLUME = 0x06E
MAIN_EVENT_FLAGS = 0x07E
MAIN_DSP_FAULT_FLAGS = 0x07F
MAIN_STOCK094_MUTE_LATCH = 0x094
MAIN_INPUT_SELECT = 0x099
MAIN_INPUT_MIRROR = 0x0B3
TAS_VOLUME_SUBADDR = 0x30
MAIN_DIAG_BASE = 0x2E5
MAIN_DIAG_RESET_BASE = 0x2ED
MAIN_DIAG_NAMES = ("I", "D", "S", "B", "R", "A", "P")
MAIN_RESET_NAMES = ("O", "V", "W", "X")

PRESET_A_EEPROM_BASE = 0x60
PRESET_B_EEPROM_BASE = 0x83
FILENAME_LEN = 0x1E
FILENAME_RAM_BASE = 0x2C0
FILENAME_DIRTY_FLAGS = 0x0BD

FNAME_CACHE = 0x220
FNAME_LEN = 0x23E
FNAME_EXPECTED_LEN = 0x23F
FNAME_FLAGS = 0x240
FNAME_ID = 0x242
FNAME_SCROLL_OFF = 0x243
FNAME_DEADLINE_LO = 0x257
FNAME_DEADLINE_HI = 0x258
FNAME_RENDER_COL = 0x259
FNAME_RENDER_OFF = 0x25A
FNAME_VALID_MASK = 0x01
FNAME_PENDING_MASK = 0x02
FNAME_ROW_DIRTY_MASK = 0x08
FNAME_ARMED_MASK = 0x10
FNAME_LEN_SEEN_MASK = 0x40

DIAG_PRESENT = 0x197
DIAG_PB1_BASE = 0x180
DIAG_PB2_BASE = 0x18B

HID_REPORT_LEN = 64
CMD03_FILENAME_READ = 0x08
CMD03_FILENAME_WRITE = 0x09
CMD03_FILENAME_ERASE = 0x0A

UNPRINTABLE_REPLACEMENT = "\ufffd"


def _json_default(obj: object) -> object:
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, bytes):
        return obj.hex()
    if isinstance(obj, tuple):
        return list(obj)
    raise TypeError(f"cannot encode {type(obj).__name__}")


def _duration_seconds(raw: str) -> float:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)([smh]?)\s*", raw)
    if not match:
        raise argparse.ArgumentTypeError(f"invalid duration {raw!r}; use 30s, 10m, or 6h")
    value = float(match.group(1))
    suffix = match.group(2) or "s"
    return value * {"s": 1.0, "m": 60.0, "h": 3600.0}[suffix]


def _seed_value(raw: str) -> int:
    if raw == "auto":
        return secrets.randbits(64)
    return int(raw, 0)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _slot_bytes(name: str) -> bytes:
    out = bytearray([0xFF] * FILENAME_LEN)
    raw = name.encode("ascii", errors="ignore")[:FILENAME_LEN]
    out[: len(raw)] = raw
    return bytes(out)


def _slot_for_cmd03(name: str) -> bytes:
    return bytes(0x00 if b in (0x00, 0xFF) else b for b in _slot_bytes(name))


def _decode_slot(raw: list[int] | bytes) -> str:
    out: list[str] = []
    for b in raw[:FILENAME_LEN]:
        v = int(b) & 0xFF
        if v in (0x00, 0xFF):
            break
        if 0x20 <= v < 0x7F:
            out.append(chr(v))
        else:
            out.append("?")
    return "".join(out)


def _compact_stats(stats: dict[str, Any]) -> dict[str, Any]:
    """Keep I2C/SRC stats useful without writing 256-entry zero-heavy arrays."""
    out: dict[str, Any] = {}
    for key, value in stats.items():
        if isinstance(value, list):
            nonzero = {str(idx): int(v) for idx, v in enumerate(value) if int(v)}
            out[key] = nonzero
        else:
            out[key] = value
    return out


class JsonlWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", encoding="utf-8")

    def write(self, obj: dict[str, Any]) -> None:
        self._fh.write(json.dumps(obj, sort_keys=True, default=_json_default) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


@dataclass
class SessionConfig:
    session_id: int
    campaign: str
    seed: int
    slot_a_pb1: str
    slot_b_pb1: str
    slot_a_pb2: str
    slot_b_pb2: str
    src_initial: str
    active_preset: str
    reset_source: str


@dataclass
class Incident:
    severity: str
    oracle: str
    symptom: str
    expected_rule: str
    observed: dict[str, Any]
    suspected_subsystem: str
    signature: str


@dataclass
class RunStats:
    sessions: int = 0
    events: int = 0
    observations: int = 0
    incidents: Counter[str] = field(default_factory=Counter)
    duplicate_incidents: Counter[str] = field(default_factory=Counter)
    campaigns: Counter[str] = field(default_factory=Counter)
    stimulus: Counter[str] = field(default_factory=Counter)


class Explorer:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.seed = _seed_value(args.seed)
        self.rng = random.Random(self.seed)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_dir = Path(args.out_dir) / f"{timestamp}_{self.seed:016x}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.events = JsonlWriter(self.run_dir / "events.jsonl")
        self.observations = JsonlWriter(self.run_dir / "observations.jsonl")
        self.snapshots = JsonlWriter(self.run_dir / "snapshots.jsonl")
        self.incidents = JsonlWriter(self.run_dir / "incidents.jsonl")
        self.stats = RunStats()
        self.seen_incidents: set[str] = set()
        self.recent_events: deque[dict[str, Any]] = deque(maxlen=25)
        self.last_status = time.monotonic()
        self.deadline = time.monotonic() + args.duration_seconds
        self.control_hex = Path(args.control_hex).resolve()
        self.main_hex = Path(args.main_hex).resolve()
        self.manifest = self._manifest()
        (self.run_dir / "manifest.json").write_text(
            json.dumps(self.manifest, indent=2, sort_keys=True, default=_json_default) + "\n",
            encoding="utf-8",
        )
        (self.run_dir / "replay.json").write_text(
            json.dumps(
                {
                    "format": "dlcp-chain-exploratory-replay-v1",
                    "manifest": "manifest.json",
                    "events": "events.jsonl",
                    "note": "Replay support is action-level; use --replay <run-dir> --session-id N.",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def close(self) -> None:
        self.events.close()
        self.observations.close()
        self.snapshots.close()
        self.incidents.close()

    def _manifest(self) -> dict[str, Any]:
        return {
            "format": "dlcp-chain-exploratory-v1",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "seed": f"0x{self.seed:016x}",
            "duration_seconds": self.args.duration_seconds,
            "campaign": self.args.campaign,
            "control_hex": str(self.control_hex),
            "control_hex_sha256": _sha256(self.control_hex),
            "main_hex": str(self.main_hex),
            "main_hex_sha256": _sha256(self.main_hex),
            "spec": str(PROJECT_ROOT / "docs" / "SIM_CHAIN_EXPLORATORY_STRESS_SPEC.md"),
            "command": sys.argv,
        }

    def _log_event(
        self,
        session_id: int,
        action: str,
        params: dict[str, Any],
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.stats.events += 1
        self.stats.stimulus[action] += 1
        event = {
            "event_id": self.stats.events,
            "wall_time": time.time(),
            "session_id": session_id,
            "action": action,
            "params": params,
            "result": result or {},
        }
        self.events.write(event)
        self.recent_events.append(event)
        return event

    def _record_incident(
        self,
        chain: Chain,
        session_id: int,
        config: SessionConfig,
        incident: Incident,
    ) -> None:
        if incident.signature in self.seen_incidents:
            self.stats.duplicate_incidents[incident.signature] += 1
            return
        self.seen_incidents.add(incident.signature)
        self.stats.incidents[incident.severity] += 1
        incident_id = f"EXP-{sum(self.stats.incidents.values()):06d}"
        snapshot = self._sample(chain, session_id, config, kind="incident")
        record = {
            "incident_id": incident_id,
            "severity": incident.severity,
            "oracle": incident.oracle,
            "seed": f"0x{self.seed:016x}",
            "campaign": config.campaign,
            "session_id": session_id,
            "tick": snapshot.get("tick"),
            "symptom": incident.symptom,
            "expected_rule": incident.expected_rule,
            "observed": incident.observed,
            "suspected_subsystem": incident.suspected_subsystem,
            "signature": incident.signature,
            "last_events": list(self.recent_events),
            "snapshot": snapshot,
            "replay_status": "not_replayed",
        }
        self.incidents.write(record)
        print(
            f"[incident] {incident_id} {incident.severity} {incident.oracle}: "
            f"{incident.symptom}",
            flush=True,
        )

    def _campaign_choice(self) -> str:
        if self.args.campaign != "all":
            return self.args.campaign
        choices = [
            ("ui", 20),
            ("preset-filename", 15),
            ("src", 15),
            ("standby-reset", 15),
            ("diag", 15),
            ("saturation", 10),
            ("fault-recovery", 10),
        ]
        total = sum(weight for _name, weight in choices)
        pick = self.rng.randrange(total)
        acc = 0
        for name, weight in choices:
            acc += weight
            if pick < acc:
                return name
        return choices[-1][0]

    def _name_choice(self) -> str:
        names = [
            "",
            "A",
            "Flat",
            "Night Mode",
            "LX521.4 PB6v23 Q",
            "LX521 V15 L22MG old_NC100",
            "Long preset name scroll tail first",
            "Name_With_Underscore_123456789",
            "bad\x01name",
        ]
        return self.rng.choice(names)

    def _session_config(self, session_id: int) -> SessionConfig:
        campaign = self._campaign_choice()
        pair_mode = self.rng.choice(["match", "mismatch", "blank-pb2", "blank-a", "blank-b"])
        a = self._name_choice()
        b = self._name_choice()
        if pair_mode == "match":
            a2, b2 = a, b
        elif pair_mode == "blank-pb2":
            a2, b2 = "", ""
        elif pair_mode == "blank-a":
            a, a2 = "", ""
            b2 = b
        elif pair_mode == "blank-b":
            b, b2 = "", ""
            a2 = a
        else:
            a2, b2 = self._name_choice(), self._name_choice()
        return SessionConfig(
            session_id=session_id,
            campaign=campaign,
            seed=self.rng.getrandbits(64),
            slot_a_pb1=a,
            slot_b_pb1=b,
            slot_a_pb2=a2,
            slot_b_pb2=b2,
            src_initial=self.rng.choice(["locked", "lost", "non_pcm", "flap"]),
            active_preset=self.rng.choice(["A", "B"]),
            reset_source=self.rng.choice(["por", "bor", "mclr"]),
        )

    def _new_chain(self, config: SessionConfig) -> Chain:
        chain = Chain.from_v171_v32(
            control_hex_path=str(self.control_hex),
            main_hex_path=str(self.main_hex),
        )
        for unit, (slot_a, slot_b) in enumerate(
            (
                (config.slot_a_pb1, config.slot_b_pb1),
                (config.slot_a_pb2, config.slot_b_pb2),
            )
        ):
            for offset, value in enumerate(_slot_bytes(slot_a)):
                chain.write_main_eeprom_byte(unit, PRESET_A_EEPROM_BASE + offset, value)
            for offset, value in enumerate(_slot_bytes(slot_b)):
                chain.write_main_eeprom_byte(unit, PRESET_B_EEPROM_BASE + offset, value)
        self._log_event(config.session_id, "init", config.__dict__)
        if config.reset_source != "por":
            try:
                chain.apply_reset_all(config.reset_source)
                self._log_event(config.session_id, "apply_reset_all", {"source": config.reset_source})
            except Exception as exc:
                self._log_event(
                    config.session_id,
                    "apply_reset_all_error",
                    {"source": config.reset_source},
                    {"error": repr(exc)},
                )
        return chain

    def _configure_after_boot(self, chain: Chain, config: SessionConfig) -> None:
        # IR profile DE-MASKED: do NOT overwrite the IR command map.  The V1.73
        # firmware loads its real profile-0x04 map at boot (forced via the
        # EEPROM[0x71]!=0x04 -> 0x04 path), and IR stimuli use the real Hypex
        # codes in IR_CMDS.  Record what the firmware actually loaded so the
        # oracle can spot a broken/empty profile map (e.g. configurable commands
        # that silently fail while the hardcoded preset shortcuts still work).
        loaded_profile = chain.read_reg(CONTROL_IR_PROFILE_SEL)
        loaded_ir_addr = chain.read_reg(IR_PROFILE_ADDR)
        loaded_ir_cmds = [chain.read_reg(IR_PROFILE_POWER + i) for i in range(6)]
        if config.src_initial == "locked":
            for unit in (0, 1):
                chain.poke_main_src4382_reg(unit, 0x12, 0x00)
                chain.poke_main_src4382_reg(unit, 0x13, 0x01)
        elif config.src_initial == "lost":
            for unit in (0, 1):
                chain.poke_main_src4382_reg(unit, 0x13, 0x00)
        elif config.src_initial == "non_pcm":
            for unit in (0, 1):
                chain.poke_main_src4382_reg(unit, 0x12, 0x01)
                chain.poke_main_src4382_reg(unit, 0x13, 0x01)
        self._log_event(
            config.session_id,
            "post_boot_config",
            {
                "src_initial": config.src_initial,
                "ir_profile_sel": loaded_profile,
                "ir_addr_cfg": loaded_ir_addr,
                "ir_cmd_cfg": loaded_ir_cmds,
            },
        )

    def _sample(
        self,
        chain: Chain,
        session_id: int,
        config: SessionConfig,
        *,
        kind: str,
    ) -> dict[str, Any]:
        ctl_tx = chain.ctl_tx_record_since_last_capture()
        ctl_rx = chain.ctl_rx_record_since_last_capture()
        main0_rx = chain.main0_rx_record_since_last_capture()
        main1_rx = chain.main1_rx_record_since_last_capture()
        main0_tx = chain.tx_record_since_last_capture()
        main1_tx = chain.main1_tx_record_since_last_capture()
        chain.mark_ctl_tx_capture_point()
        chain.mark_ctl_rx_capture_point()
        chain.mark_main0_rx_capture_point()
        chain.mark_main1_rx_capture_point()
        chain.mark_tx_capture_point()
        chain.mark_main1_tx_capture_point()
        main_diag = []
        for unit in (0, 1):
            main_diag.append(
                {
                    "unit": unit,
                    "active_flags": chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS),
                    "active_preset": (
                        chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS) & MAIN_ACTIVE_PRESET_MASK
                    )
                    >> 2,
                    "active_gate": (
                        chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS) & MAIN_ACTIVE_GATE_MASK
                    )
                    >> 3,
                    "preset_job_state": chain.read_main_reg(unit, MAIN_PRESET_JOB_STATE),
                    "preset_job_target": chain.read_main_reg(unit, MAIN_PRESET_JOB_TARGET),
                    "mute_latch": chain.read_main_reg(unit, MAIN_STOCK094_MUTE_LATCH),
                    "event_flags": chain.read_main_reg(unit, MAIN_EVENT_FLAGS),
                    "dsp_fault_flags": chain.read_main_reg(unit, MAIN_DSP_FAULT_FLAGS),
                    "logical_volume": chain.read_main_reg(unit, MAIN_LOGICAL_VOLUME),
                    "computed_volume": chain.read_main_reg(unit, MAIN_COMPUTED_VOLUME),
                    "input_select": chain.read_main_reg(unit, MAIN_INPUT_SELECT),
                    "input_mirror": chain.read_main_reg(unit, MAIN_INPUT_MIRROR),
                    # TAS3108 volume-coefficient (0x30) write history: the
                    # ground truth for mute-leak detection (a non-zero 0x30
                    # write while mute_latch is set = audio returning).
                    "tas30_last_write": (
                        chain.read_main_dsp_write_payload(unit, TAS_VOLUME_SUBADDR) or b""
                    ).hex(),
                    "tas30_write_count": len(
                        chain.read_main_dsp_write_payloads(unit, TAS_VOLUME_SUBADDR)
                    ),
                    # ACTUAL DSP preset-coefficient fingerprint.  The biquad
                    # range 0x37..0x90 (per test_v171_v32_dual_main_preset_sync)
                    # is the preset-defining coefficient block; it EXCLUDES
                    # volume (0x30) so the digest changes on a preset switch but
                    # not on a volume change.  Lets the oracle verify
                    # preset A -> coeffs A / preset B -> coeffs B, that PB1 and
                    # PB2 hold byte-identical coeffs, and that a preset flag flip
                    # actually rewrote the coefficients (not a silent no-op).
                    "dsp_biquad_digest": hashlib.sha256(
                        bytes(chain.read_main_dsp_reg(unit, s) for s in range(0x37, 0x91))
                    ).hexdigest()[:12],
                    "dsp_full_digest": hashlib.sha256(
                        bytes(chain.read_main_dsp_reg(unit, s) for s in range(0x00, 0x100))
                    ).hexdigest()[:12],
                    "diag": {
                        name: chain.read_main_reg(unit, MAIN_DIAG_BASE + idx)
                        for idx, name in enumerate(MAIN_DIAG_NAMES)
                    },
                    "reset": {
                        name: chain.read_main_reg(unit, MAIN_DIAG_RESET_BASE + idx)
                        for idx, name in enumerate(MAIN_RESET_NAMES)
                    },
                    "src_stats": _compact_stats(chain.read_main_src4382_stats(unit)),
                    "tas_stats": _compact_stats(chain.read_main_tas3108_stats(unit)),
                    "filename_ram": _decode_slot(
                        [chain.read_main_reg(unit, FILENAME_RAM_BASE + i) for i in range(FILENAME_LEN)]
                    ),
                    "filename_dirty_flags": chain.read_main_reg(unit, FILENAME_DIRTY_FLAGS),
                }
            )
        lcd = chain.lcd_lines()
        sample = {
            "kind": kind,
            "session_id": session_id,
            "campaign": config.campaign,
            "tick": chain.current_tick(),
            "lcd": list(lcd),
            "is_connected": chain.is_connected(),
            "is_waiting": chain.is_waiting(),
            "control": {
                "flags": chain.read_reg(CONTROL_FLAGS),
                "display_state": chain.read_reg(DISPLAY_STATE_INDEX),
                "volume": chain.read_reg(VOLUME_CACHE),
                "input": chain.read_reg(INPUT_CACHE),
                "diag_present": chain.read_reg(DIAG_PRESENT),
                "diag_pb1": [
                    chain.read_reg(DIAG_PB1_BASE + i) for i in range(11)
                ],
                "diag_pb2": [
                    chain.read_reg(DIAG_PB2_BASE + i) for i in range(11)
                ],
                "fname": {
                    "flags": chain.read_reg(FNAME_FLAGS),
                    "len": chain.read_reg(FNAME_LEN),
                    "expected_len": chain.read_reg(FNAME_EXPECTED_LEN),
                    "id": chain.read_reg(FNAME_ID),
                    "scroll_off": chain.read_reg(FNAME_SCROLL_OFF),
                    "deadline": chain.read_reg(FNAME_DEADLINE_LO)
                    | (chain.read_reg(FNAME_DEADLINE_HI) << 8),
                    "render_col": chain.read_reg(FNAME_RENDER_COL),
                    "render_off": chain.read_reg(FNAME_RENDER_OFF),
                    "cache": _decode_slot([chain.read_reg(FNAME_CACHE + i) for i in range(FILENAME_LEN)]),
                },
            },
            "main": main_diag,
            "bridge": chain.bridge_byte_stats(),
            "comm": {
                "ctl_tx_len": len(ctl_tx),
                "ctl_tx_tail": ctl_tx[-24:],
                "ctl_rx_len": len(ctl_rx),
                "ctl_rx_tail": ctl_rx[-24:],
                "main0_tx_len": len(main0_tx),
                "main0_tx_tail": main0_tx[-24:],
                "main0_rx_len": len(main0_rx),
                "main0_rx_tail": main0_rx[-24:],
                "main1_tx_len": len(main1_tx),
                "main1_tx_tail": main1_tx[-24:],
                "main1_rx_len": len(main1_rx),
                "main1_rx_tail": main1_rx[-24:],
                "control_tx_frames_tail": [list(frame) for frame in chain.tx_frames()[-12:]],
            },
        }
        self.stats.observations += 1
        writer = self.snapshots if kind == "incident" else self.observations
        writer.write(sample)
        return sample

    def _oracles(
        self,
        chain: Chain,
        session_id: int,
        config: SessionConfig,
        sample: dict[str, Any],
        previous_sample: dict[str, Any] | None,
    ) -> list[Incident]:
        incidents: list[Incident] = []
        lcd_text = "".join(sample["lcd"])
        if UNPRINTABLE_REPLACEMENT in lcd_text or any(
            (ord(ch) < 0x20 or ord(ch) >= 0x7F) for ch in lcd_text if ch != " "
        ):
            incidents.append(
                Incident(
                    "MEDIUM",
                    "ui.lcd.printable",
                    f"LCD contains nonprintable/gibberish text {sample['lcd']!r}",
                    "LCD rows should render printable ASCII or spaces",
                    {"lcd": sample["lcd"]},
                    "CONTROL LCD rendering",
                    f"lcd-nonprintable:{sample['lcd']!r}",
                )
            )
        fname = sample["control"]["fname"]
        fname_flags = fname["flags"]
        if (fname_flags & FNAME_VALID_MASK) and fname["len"] != fname["expected_len"]:
            incidents.append(
                Incident(
                    "MEDIUM",
                    "protocol.filename.length",
                    "filename marked valid with len != expected_len",
                    "valid filename cache must have received_len == expected_len",
                    {"fname": fname},
                    "CONTROL filename parser",
                    "fname-valid-length-mismatch",
                )
            )
        if (fname_flags & FNAME_VALID_MASK) and (fname_flags & FNAME_PENDING_MASK):
            incidents.append(
                Incident(
                    "LOW",
                    "protocol.filename.flags",
                    "filename state has VALID and PENDING set together",
                    "settled valid cache should not remain pending",
                    {"fname": fname},
                    "CONTROL filename state",
                    "fname-valid-pending",
                )
            )
        for unit_state in sample["main"]:
            diag_bad = {
                k: v for k, v in unit_state["diag"].items() if not (0 <= int(v) <= 0x0F)
            }
            reset_bad = {
                k: v for k, v in unit_state["reset"].items() if int(v) not in (0, 1)
            }
            if diag_bad:
                incidents.append(
                    Incident(
                        "MEDIUM",
                        "diag.counter.range",
                        f"MAIN{unit_state['unit']} diag counter outside 0..15",
                        "diag counters must be saturating nibbles",
                        {"diag_bad": diag_bad, "unit": unit_state["unit"]},
                        "MAIN diagnostics",
                        f"diag-range-unit-{unit_state['unit']}",
                    )
                )
            if reset_bad:
                incidents.append(
                    Incident(
                        "LOW",
                        "diag.reset.range",
                        f"MAIN{unit_state['unit']} reset flag outside boolean range",
                        "reset flags should be binary latches",
                        {"reset_bad": reset_bad, "unit": unit_state["unit"]},
                        "MAIN reset diagnostics",
                        f"reset-range-unit-{unit_state['unit']}",
                    )
                )
        if previous_sample is not None:
            for link, stats in sample["bridge"].items():
                prev = previous_sample["bridge"].get(link, {})
                delta = int(stats.get("total_edges", 0)) - int(prev.get("total_edges", 0))
                if delta > self.args.bridge_delta_warn:
                    incidents.append(
                        Incident(
                            "LOW",
                            "link.saturation.delta",
                            f"large bridge byte delta on {link}: {delta}",
                            "one observation interval should not produce unbounded link traffic",
                            {"link": link, "delta": delta},
                            "chain UART",
                            f"bridge-delta:{link}",
                        )
                    )
        if (
            sample["is_waiting"]
            and sample["is_connected"]
            and previous_sample is not None
            and previous_sample["is_waiting"]
            and previous_sample["is_connected"]
        ):
            incidents.append(
                Incident(
                    "LOW",
                    "ui.waiting.connected",
                    "CONTROL is both connected and showing WAITING",
                    "connected steady-state UI should not be WAITING",
                    {"lcd": sample["lcd"], "control": sample["control"]},
                    "CONTROL connection/UI state",
                    "waiting-connected",
                )
            )
        return incidents

    def _navigate_for_campaign(self, chain: Chain, config: SessionConfig) -> None:
        if config.campaign == "preset-filename":
            self._safe_action(chain, config, "press", {"key": "RIGHT"})
        elif config.campaign == "diag":
            for _ in range(self.rng.choice([4, 5])):
                self._safe_action(chain, config, "press", {"key": "RIGHT"})
        elif config.campaign == "src":
            for _ in range(self.rng.choice([2, 3])):
                self._safe_action(chain, config, "press", {"key": "RIGHT"})

    def _safe_action(
        self,
        chain: Chain,
        config: SessionConfig,
        action: str,
        params: dict[str, Any],
    ) -> None:
        try:
            self._apply_action(chain, action, params)
            self._log_event(config.session_id, action, params, {"ok": True, "tick": chain.current_tick()})
        except Exception as exc:
            self._log_event(
                config.session_id,
                action,
                params,
                {"ok": False, "error": repr(exc), "tick": getattr(chain, "current_tick", lambda: -1)()},
            )
            self._record_incident(
                chain,
                config.session_id,
                config,
                Incident(
                    "LOW",
                    "runner.action.exception",
                    f"action {action} raised {exc!r}",
                    "exploratory stimuli should either apply or be logged as unsupported",
                    {"action": action, "params": params, "error": repr(exc)},
                    "runner/sim facade",
                    f"action-exception:{action}:{type(exc).__name__}",
                ),
            )

    def _apply_action(self, chain: Chain, action: str, params: dict[str, Any]) -> None:
        if action == "step":
            chain.step_ticks(int(params["ticks"]))
            return
        if action == "press":
            chain.press(str(params["key"]))
            return
        if action == "ir":
            chain.inject_decoded_ir_event(addr=IR_ADDR_HYPEX, cmd=int(params["cmd"]) & 0xFF)
            chain.step_ticks(int(params.get("settle_ticks", 8_000_000)))
            return
        if action == "host_cmd":
            chain.inject_host_command(
                cmd=int(params["cmd"]) & 0xFF,
                data=int(params["data"]) & 0xFF,
                route=int(params.get("route", 0xBF)) & 0xFF,
            )
            chain.step_ticks(int(params.get("settle_ticks", 6_000_000)))
            return
        if action == "hid_filename_write":
            report = bytearray(HID_REPORT_LEN)
            report[0] = 0x03
            report[1] = CMD03_FILENAME_WRITE
            payload = _slot_for_cmd03(str(params["name"]))
            report[2 : 2 + len(payload)] = payload
            unit = int(params["unit"])
            try:
                chain.firmware_hid_report(unit, report, max_steps=int(params.get("max_steps", 60_000)))
            except RuntimeError:
                # V3.3+ has moved enough USB code that the facade's symbol-backed
                # EP1 entry helper can fail even when direct firmware state is
                # still useful for exploratory filename/HFD churn.
                for i, value in enumerate(_slot_bytes(str(params["name"]))):
                    chain.write_main_reg(unit, FILENAME_RAM_BASE + i, value)
                chain.write_main_reg(
                    unit,
                    FILENAME_DIRTY_FLAGS,
                    chain.read_main_reg(unit, FILENAME_DIRTY_FLAGS) | 0x60,
                )
            chain.step_ticks(int(params.get("settle_ticks", 4_000_000)))
            return
        if action == "hid_filename_read":
            report = bytearray(HID_REPORT_LEN)
            report[0] = 0x03
            report[1] = CMD03_FILENAME_READ
            try:
                chain.firmware_hid_report(int(params["unit"]), report, max_steps=int(params.get("max_steps", 60_000)))
            except RuntimeError:
                pass
            chain.step_ticks(int(params.get("settle_ticks", 2_000_000)))
            return
        if action == "src_nack":
            unit = int(params["unit"])
            count = int(params["count"])
            if params.get("phase") == "data":
                chain.inject_main_src4382_data_nack(unit, count)
            else:
                chain.inject_main_src4382_address_nack(unit, count)
            chain.step_ticks(int(params.get("settle_ticks", 5_000_000)))
            return
        if action == "tas_nack":
            unit = int(params["unit"])
            count = int(params["count"])
            if params.get("phase") == "data":
                chain.inject_main_tas3108_data_nack(unit, count)
            else:
                chain.inject_main_tas3108_address_nack(unit, count)
            chain.step_ticks(int(params.get("settle_ticks", 5_000_000)))
            return
        if action == "src_reg":
            unit = int(params["unit"])
            chain.poke_main_src4382_reg(unit, int(params["reg"]), int(params["value"]))
            chain.step_ticks(int(params.get("settle_ticks", 3_000_000)))
            return
        if action == "mssp_stop":
            unit = int(params["unit"])
            chain.set_main_mssp_stop_fault(
                unit,
                stop_busy_cycles=int(params.get("cycles", 600_000)),
                stop_busy_count=int(params.get("count", 1)),
            )
            chain.step_ticks(int(params.get("fault_ticks", 8_000_000)))
            chain.clear_main_mssp_stop_faults(unit)
            chain.force_reset_main_mssp_unit(unit)
            chain.step_ticks(int(params.get("settle_ticks", 4_000_000)))
            return
        if action == "line_hold":
            chain.set_mssp_line_hold(
                scl_low=bool(params.get("scl_low", False)),
                sda_low=bool(params.get("sda_low", False)),
            )
            chain.step_ticks(int(params.get("fault_ticks", 5_000_000)))
            chain.clear_mssp_line_holds()
            chain.force_reset_main_mssp()
            chain.step_ticks(int(params.get("settle_ticks", 4_000_000)))
            return
        if action == "link_drop":
            link = str(params["link"])
            chain.set_link_fault(link, drop=True)
            chain.step_ticks(int(params.get("fault_ticks", 8_000_000)))
            chain.set_link_fault(link, drop=False)
            chain.step_ticks(int(params.get("settle_ticks", 8_000_000)))
            return
        if action == "blackout":
            chain.set_blackout(True)
            chain.step_ticks(int(params.get("fault_ticks", 10_000_000)))
            chain.set_blackout(False)
            chain.run_until_connected(limit=int(params.get("reconnect_limit", 80)))
            return
        if action == "reset_main":
            chain.apply_main_reset(int(params["unit"]), str(params.get("source", "mclr")))
            chain.step_ticks(int(params.get("settle_ticks", 20_000_000)))
            return
        if action == "reset_all":
            chain.apply_reset_all(str(params.get("source", "mclr")))
            chain.run_until_connected(limit=int(params.get("reconnect_limit", 120)))
            return
        if action == "raw_main_bytes":
            raw = bytes(int(b) & 0xFF for b in params["bytes"])
            chain.inject_main_uart_rx_bytes(int(params["unit"]), raw)
            chain.step_ticks(int(params.get("settle_ticks", 5_000_000)))
            return
        if action == "triplet":
            chain.inject_triplet(
                int(params.get("route", 0xBF)),
                int(params["cmd"]),
                int(params["data"]),
            )
            chain.step_ticks(int(params.get("settle_ticks", 4_000_000)))
            return
        if action == "an0":
            chain.set_main_an0_sample(int(params["unit"]), int(params["value"]))
            chain.step_ticks(int(params.get("settle_ticks", 4_000_000)))
            return
        if action == "ra1_edge":
            unit = int(params["unit"])
            chain.set_main_pin(unit, "A", 1, bool(params.get("level", False)))
            chain.step_ticks(int(params.get("settle_ticks", 3_000_000)))
            chain.set_main_pin(unit, "A", 1, not bool(params.get("level", False)))
            chain.step_ticks(int(params.get("settle_ticks", 3_000_000)))
            return
        raise ValueError(f"unknown action {action!r}")

    def _next_action(self, config: SessionConfig) -> tuple[str, dict[str, Any]]:
        campaign = config.campaign
        if campaign == "ui":
            return self.rng.choice(
                [
                    ("press", {"key": self.rng.choice(["RIGHT", "LEFT", "UP", "DOWN", "SELECT", "STBY"])}),
                    ("ir", {"cmd": self.rng.choice(list(IR_CMDS.values()))}),
                    ("host_cmd", {"cmd": 0x07, "data": self.rng.randrange(0x40, 0x80)}),
                    ("host_cmd", {"cmd": 0x20, "data": self.rng.randrange(2)}),
                ]
            )
        if campaign == "preset-filename":
            return self.rng.choice(
                [
                    ("press", {"key": self.rng.choice(["RIGHT", "LEFT", "UP", "DOWN"])}),
                    ("ir", {"cmd": self.rng.choice([IR_CMDS["preset_a"], IR_CMDS["preset_b"], IR_CMDS["mute"]])}),
                    ("hid_filename_write", {"unit": self.rng.randrange(2), "name": self._name_choice()}),
                    ("hid_filename_read", {"unit": self.rng.randrange(2)}),
                    ("triplet", {"cmd": self.rng.randrange(0x2D, 0x4F), "data": self.rng.randrange(256)}),
                ]
            )
        if campaign == "src":
            return self.rng.choice(
                [
                    ("host_cmd", {"cmd": 0x06, "data": self.rng.randrange(0, 8)}),
                    ("ir", {"cmd": self.rng.choice([IR_CMDS["input_up"], IR_CMDS["input_down"]])}),
                    ("src_reg", {"unit": self.rng.randrange(2), "reg": 0x13, "value": self.rng.choice([0, 1, 2, 0x80])}),
                    ("src_reg", {"unit": self.rng.randrange(2), "reg": 0x12, "value": self.rng.choice([0, 1, 2])}),
                    ("src_nack", {"unit": self.rng.randrange(2), "phase": self.rng.choice(["address", "data"]), "count": self.rng.randrange(1, 8)}),
                ]
            )
        if campaign == "standby-reset":
            return self.rng.choice(
                [
                    ("ir", {"cmd": self.rng.choice([IR_CMDS["standby"], IR_CMDS["wake"], IR_CMDS["power"]])}),
                    ("press", {"key": "STBY"}),
                    ("blackout", {"fault_ticks": self.rng.randrange(2_000_000, 20_000_000)}),
                    ("reset_main", {"unit": self.rng.randrange(2), "source": self.rng.choice(["mclr", "bor", "wdt", "reset"])}),
                    ("reset_all", {"source": self.rng.choice(["mclr", "bor"])}),
                    ("an0", {"unit": self.rng.randrange(2), "value": self.rng.choice([0x0100, 0x0227, 0x0300])}),
                ]
            )
        if campaign == "diag":
            return self.rng.choice(
                [
                    ("press", {"key": self.rng.choice(["RIGHT", "LEFT", "UP", "DOWN"])}),
                    ("src_nack", {"unit": self.rng.randrange(2), "phase": self.rng.choice(["address", "data"]), "count": self.rng.randrange(1, 4)}),
                    ("tas_nack", {"unit": self.rng.randrange(2), "phase": self.rng.choice(["address", "data"]), "count": self.rng.randrange(1, 6)}),
                    ("ra1_edge", {"unit": self.rng.randrange(2), "level": self.rng.choice([False, True])}),
                    ("an0", {"unit": self.rng.randrange(2), "value": self.rng.choice([0x0100, 0x0300])}),
                    ("ir", {"cmd": self.rng.choice([IR_CMDS["volume_up"], IR_CMDS["mute"], IR_CMDS["standby"], IR_CMDS["wake"]])}),
                ]
            )
        if campaign == "saturation":
            return self.rng.choice(
                [
                    ("raw_main_bytes", {"unit": self.rng.randrange(2), "bytes": [self.rng.randrange(256) for _ in range(self.rng.randrange(1, 80))]}),
                    ("triplet", {"cmd": self.rng.randrange(0, 0x50), "data": self.rng.randrange(256)}),
                    ("link_drop", {"link": self.rng.choice(["ctl_to_m0", "m0_to_m1", "m1_to_ctl"])}),
                    ("host_cmd", {"cmd": self.rng.randrange(0, 0x45), "data": self.rng.randrange(256)}),
                ]
            )
        return self.rng.choice(
            [
                ("src_nack", {"unit": self.rng.randrange(2), "phase": self.rng.choice(["address", "data"]), "count": self.rng.randrange(1, 12)}),
                ("tas_nack", {"unit": self.rng.randrange(2), "phase": self.rng.choice(["address", "data"]), "count": self.rng.randrange(1, 12)}),
                ("mssp_stop", {"unit": self.rng.randrange(2), "cycles": self.rng.randrange(100_000, 1_500_000), "count": self.rng.choice([1, 2])}),
                ("line_hold", {"scl_low": self.rng.choice([True, False]), "sda_low": self.rng.choice([True, False])}),
                ("host_cmd", {"cmd": 0x07, "data": self.rng.randrange(0x40, 0x80)}),
            ]
        )

    def run(self) -> int:
        session_id = 0
        try:
            while time.monotonic() < self.deadline:
                if self.args.max_sessions and session_id >= self.args.max_sessions:
                    break
                session_id += 1
                config = self._session_config(session_id)
                self.stats.sessions += 1
                self.stats.campaigns[config.campaign] += 1
                self._run_session(config)
                self._status(force=False)
        finally:
            self._write_summary()
            self.close()
        return 0

    def _run_session(self, config: SessionConfig) -> None:
        chain = self._new_chain(config)
        previous: dict[str, Any] | None = None
        try:
            chunks = chain.run_until_connected(limit=self.args.connect_limit)
            self._log_event(config.session_id, "run_until_connected", {"limit": self.args.connect_limit}, {"chunks": chunks, "connected": chain.is_connected(), "lcd": chain.lcd_lines()})
            if not chain.is_connected():
                self._record_incident(
                    chain,
                    config.session_id,
                    config,
                    Incident(
                        "HIGH",
                        "liveness.boot-connect",
                        "chain did not reach connected steady-state during warmup",
                        "booted release chain should reach connected Volume screen",
                        {"chunks": chunks, "lcd": chain.lcd_lines()},
                        "boot/full-sync",
                        f"boot-connect:{config.campaign}:{config.reset_source}",
                    ),
                )
                return
            self._configure_after_boot(chain, config)
            chain.mark_ctl_tx_capture_point()
            chain.mark_ctl_rx_capture_point()
            chain.mark_main0_rx_capture_point()
            chain.mark_main1_rx_capture_point()
            chain.mark_tx_capture_point()
            chain.mark_main1_tx_capture_point()
            self._navigate_for_campaign(chain, config)
            max_events = self.rng.randrange(self.args.session_events_min, self.args.session_events_max + 1)
            for _ in range(max_events):
                if time.monotonic() >= self.deadline:
                    break
                action, params = self._next_action(config)
                self._safe_action(chain, config, action, params)
                # Always add a little unscripted foreground time after a stimulus.
                if self.rng.random() < 0.7:
                    self._safe_action(
                        chain,
                        config,
                        "step",
                        {"ticks": self.rng.randrange(1_000_000, 12_000_000)},
                    )
                sample = self._sample(chain, config.session_id, config, kind="observation")
                for incident in self._oracles(chain, config.session_id, config, sample, previous):
                    self._record_incident(chain, config.session_id, config, incident)
                previous = sample
                self._status(force=False)
        except Exception as exc:
            try:
                self._record_incident(
                    chain,
                    config.session_id,
                    config,
                    Incident(
                        "MEDIUM",
                        "runner.session.exception",
                        f"session raised {exc!r}",
                        "exploratory session should not crash the runner",
                        {"error": repr(exc)},
                        "runner/sim facade",
                        f"session-exception:{type(exc).__name__}",
                    ),
                )
            except Exception:
                raise

    def _status(self, *, force: bool) -> None:
        now = time.monotonic()
        if not force and now - self.last_status < self.args.status_interval:
            return
        self.last_status = now
        remaining = max(0.0, self.deadline - now)
        print(
            "[explore] "
            f"sessions={self.stats.sessions} events={self.stats.events} "
            f"incidents={dict(self.stats.incidents)} dup={sum(self.stats.duplicate_incidents.values())} "
            f"remaining={remaining/60:.1f}m artifacts={self.run_dir}",
            flush=True,
        )

    def _write_summary(self) -> None:
        summary = [
            "# DLCP Chain Exploratory Campaign Summary",
            "",
            f"- Artifact dir: `{self.run_dir}`",
            f"- Seed: `0x{self.seed:016x}`",
            f"- CONTROL: `{self.control_hex}`",
            f"- MAIN: `{self.main_hex}`",
            f"- Sessions: {self.stats.sessions}",
            f"- Events: {self.stats.events}",
            f"- Observations: {self.stats.observations}",
            f"- Incidents: {dict(self.stats.incidents)}",
            f"- Duplicate incident signatures: {sum(self.stats.duplicate_incidents.values())}",
            f"- Campaigns: {dict(self.stats.campaigns)}",
            f"- Stimulus counts: {dict(self.stats.stimulus)}",
            "",
            "## Files",
            "",
            "- `manifest.json`: release identity, command, seed.",
            "- `events.jsonl`: generated initial conditions and action stream.",
            "- `observations.jsonl`: sampled LCD, UART stats, SRC/TAS, diagnostics, filename state.",
            "- `snapshots.jsonl`: incident snapshots.",
            "- `incidents.jsonl`: deduplicated abnormal findings.",
            "- `replay.json`: replay metadata.",
        ]
        (self.run_dir / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
        print(f"[explore] summary written: {self.run_dir / 'summary.md'}", flush=True)


def _load_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))
    return events


def replay(args: argparse.Namespace) -> int:
    run_dir = Path(args.replay).resolve()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    events = _load_events(run_dir / "events.jsonl")
    session_id = args.session_id
    session_events = [e for e in events if int(e["session_id"]) == session_id]
    if not session_events:
        raise SystemExit(f"no events for session {session_id} in {run_dir}")
    init = next((e for e in session_events if e["action"] == "init"), None)
    if init is None:
        raise SystemExit(f"session {session_id} has no init event")
    cfg = SessionConfig(**init["params"])
    explorer_args = argparse.Namespace(
        **{
            **vars(args),
            "seed": manifest["seed"],
            "duration_seconds": 1,
            "campaign": cfg.campaign,
            "control_hex": manifest["control_hex"],
            "main_hex": manifest["main_hex"],
            "out_dir": str(run_dir.parent / f"replay_{session_id}"),
            "bridge_delta_warn": 1000000,
            "connect_limit": args.connect_limit,
            "session_events_min": 1,
            "session_events_max": 1,
            "max_sessions": 1,
            "status_interval": 999999,
        }
    )
    exp = Explorer(explorer_args)
    chain = exp._new_chain(cfg)
    chain.run_until_connected(limit=args.connect_limit)
    exp._configure_after_boot(chain, cfg)
    for event in session_events:
        action = event["action"]
        if action in {
            "init",
            "apply_reset_all",
            "run_until_connected",
            "post_boot_config",
        } or action.endswith("_error"):
            continue
        exp._safe_action(chain, cfg, action, event["params"])
    sample = exp._sample(chain, session_id, cfg, kind="replay-final")
    exp._write_summary()
    exp.close()
    print(json.dumps({"replayed_session": session_id, "final_lcd": sample["lcd"], "out": str(exp.run_dir)}, indent=2))
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", default="10m", help="wall-clock duration, e.g. 30s, 10m, 6h")
    parser.add_argument("--seed", default="auto", help="integer seed or auto")
    parser.add_argument("--campaign", default="all")
    parser.add_argument("--control-hex", default=str(V173_CONTROL_HEX))
    parser.add_argument("--main-hex", default=str(V34_MAIN_HEX))
    parser.add_argument("--out-dir", default=str(SIM_ARTIFACTS_DIR / "exploratory"))
    parser.add_argument("--stop-after-high", type=int, default=0, help="reserved for future use")
    parser.add_argument("--max-sessions", type=int, default=0)
    parser.add_argument("--session-events-min", type=int, default=20)
    parser.add_argument("--session-events-max", type=int, default=60)
    parser.add_argument("--connect-limit", type=int, default=240)
    parser.add_argument("--bridge-delta-warn", type=int, default=2000)
    parser.add_argument("--status-interval", type=float, default=30.0)
    parser.add_argument("--replay", help="artifact directory to replay")
    parser.add_argument("--session-id", type=int, default=1, help="session id for --replay")
    args = parser.parse_args(argv)
    args.duration_seconds = _duration_seconds(args.duration)
    if args.session_events_min <= 0 or args.session_events_max < args.session_events_min:
        parser.error("--session-events-min/max must define a positive inclusive range")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.replay:
        return replay(args)
    explorer = Explorer(args)
    print(
        f"[explore] run_dir={explorer.run_dir} seed=0x{explorer.seed:016x} "
        f"duration={args.duration_seconds:.1f}s",
        flush=True,
    )
    return explorer.run()


if __name__ == "__main__":
    raise SystemExit(main())
