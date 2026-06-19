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

from dlcp_fw.paths import PROJECT_ROOT, SIM_ARTIFACTS_DIR, V173_CONTROL_HEX, V35_MAIN_HEX
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
MAIN_ACTIVE_MUTE_MASK = 0x10
MAIN_PRESET_JOB_STATE = 0x2DE
MAIN_PRESET_JOB_TARGET = 0x2DF
MAIN_PRESET_JOB_INDEX = 0x2E0
MAIN_PRESET_JOB_FLAGS = 0x2E2
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
TAS_BIQUAD_FIRST = 0x37
TAS_BIQUAD_LAST = 0x90
TAS_BIQUAD_SUBADDRS = tuple(range(TAS_BIQUAD_FIRST, TAS_BIQUAD_LAST + 1))
DSP_FAULT_MASK = 0x40
DSP_ACKSTAT_MASK = 0x04
SRC_REG_NON_PCM = 0x12
SRC_REG_RX_STATUS = 0x13
SRC_REG_RX_LOCK = 0x14
SRC_LOCKED_REGS = {
    SRC_REG_NON_PCM: 0x00,
    SRC_REG_RX_STATUS: 0x01,
    SRC_REG_RX_LOCK: 0x00,
}
SRC_RXCKR_HOLE_REGS = {
    SRC_REG_NON_PCM: 0x00,
    SRC_REG_RX_STATUS: 0x00,
    SRC_REG_RX_LOCK: 0x00,
}
SRC_REG_HEX_KEYS = {
    SRC_REG_NON_PCM: f"0x{SRC_REG_NON_PCM:02X}",
    SRC_REG_RX_STATUS: f"0x{SRC_REG_RX_STATUS:02X}",
    SRC_REG_RX_LOCK: f"0x{SRC_REG_RX_LOCK:02X}",
}
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
GOLDEN_SETTLE_TICKS = 260_000_000
PHASE_SAMPLE_TICKS = 250_000
PHASE_SAMPLE_COUNT = 260
PHASE_SWEEP_DELAYS = (
    0,
    250_000,
    500_000,
    1_000_000,
    2_000_000,
    4_000_000,
    8_000_000,
    12_000_000,
)
PHASE_SWEEP_JITTER = 250_000


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


def _digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def _dsp_biquad_image(chain: Chain, unit: int) -> bytes:
    return bytes(chain.read_main_dsp_reg(unit, subaddr) for subaddr in TAS_BIQUAD_SUBADDRS)


def _golden_summary(
    golden_images: dict[int, dict[int, bytes]],
) -> dict[str, Any]:
    return {
        "range": f"0x{TAS_BIQUAD_FIRST:02X}..0x{TAS_BIQUAD_LAST:02X}",
        "units": {
            str(unit): {
                ("B" if preset else "A"): {
                    "digest": _digest_bytes(image),
                    "image": image.hex(),
                }
                for preset, image in per_preset.items()
            }
            for unit, per_preset in golden_images.items()
        },
    }


def _set_src_regs(chain: Chain, unit: int, values: dict[int, int]) -> None:
    for reg, value in values.items():
        chain.poke_main_src4382_reg(unit, reg, value)


def _set_all_src_locked(chain: Chain) -> None:
    for unit in (0, 1):
        _set_src_regs(chain, unit, SRC_LOCKED_REGS)


def _send_ir_preset(chain: Chain, preset_b: bool) -> None:
    chain.inject_decoded_ir_event(
        addr=IR_ADDR_HYPEX,
        cmd=IR_CMDS["preset_b"] if preset_b else IR_CMDS["preset_a"],
    )


def learn_preset_golden_images(
    control_hex: Path | str,
    main_hex: Path | str,
) -> dict[int, dict[int, bytes]]:
    """Learn stable clean A/B TAS 0x37..0x90 images for each MAIN unit."""
    chain = Chain.from_v171_v32(
        control_hex_path=str(control_hex),
        main_hex_path=str(main_hex),
    )
    chunks = chain.run_until_connected(limit=300)
    if chunks >= 300 or not chain.is_connected():
        raise RuntimeError("golden coeff learner could not reach connected chain")
    _set_all_src_locked(chain)
    chain.step_ticks(4 * 48_000_000)

    _send_ir_preset(chain, True)
    chain.step_ticks(GOLDEN_SETTLE_TICKS)
    for unit in (0, 1):
        if chain.read_main_reg(unit, MAIN_PRESET_JOB_STATE):
            raise RuntimeError(f"golden coeff learner preset B did not settle on unit {unit}")
    b_images = {unit: _dsp_biquad_image(chain, unit) for unit in (0, 1)}

    _send_ir_preset(chain, False)
    chain.step_ticks(GOLDEN_SETTLE_TICKS)
    for unit in (0, 1):
        if chain.read_main_reg(unit, MAIN_PRESET_JOB_STATE):
            raise RuntimeError(f"golden coeff learner preset A did not settle on unit {unit}")
    a_images = {unit: _dsp_biquad_image(chain, unit) for unit in (0, 1)}

    return {
        unit: {
            0: a_images[unit],
            1: b_images[unit],
        }
        for unit in (0, 1)
    }


def _image_diff(expected: bytes, observed: bytes) -> list[dict[str, int]]:
    diffs = []
    for offset, (exp, got) in enumerate(zip(expected, observed)):
        if exp != got:
            diffs.append(
                {
                    "subaddr": TAS_BIQUAD_FIRST + offset,
                    "expected": exp,
                    "observed": got,
                }
            )
    return diffs


def _int_from_hex(raw: str) -> int:
    if not raw:
        return 0
    return int(raw, 16)


def _tas_write_tail(chain: Chain | None, unit: int, subaddr: int) -> list[str]:
    if chain is None:
        return []
    try:
        return [payload.hex() for payload in chain.read_main_dsp_write_payloads(unit, subaddr)[-4:]]
    except Exception:
        return []


def _src_regs_indicate_live_pcm(unit_state: dict[str, Any]) -> bool:
    regs = unit_state.get("src_regs", {})
    rx_status = int(regs.get(SRC_REG_HEX_KEYS[SRC_REG_RX_STATUS], 0))
    non_pcm = int(regs.get(SRC_REG_HEX_KEYS[SRC_REG_NON_PCM], 0))
    return (rx_status & 0x03) != 0 and (non_pcm & 0x01) == 0


def _golden_coeff_incident(
    sample: dict[str, Any],
    unit_state: dict[str, Any],
    golden_images: dict[int, dict[int, bytes]] | None,
    *,
    chain: Chain | None = None,
    recent_events: list[dict[str, Any]] | None = None,
) -> Incident | None:
    if not golden_images:
        return None
    unit = int(unit_state["unit"])
    active_flags = int(unit_state["active_flags"])
    preset = int(unit_state["active_preset"])
    image_hex = str(unit_state.get("dsp_biquad_image", ""))
    if not image_hex:
        return None
    src_live_pcm = _src_regs_indicate_live_pcm(unit_state)
    live = (
        int(unit_state.get("preset_job_state", 0)) == 0
        and bool(active_flags & MAIN_ACTIVE_GATE_MASK)
        and not bool(active_flags & MAIN_ACTIVE_MUTE_MASK)
        and src_live_pcm
        and _int_from_hex(str(unit_state.get("tas30_last_write", ""))) != 0
        and (int(unit_state.get("dsp_fault_flags", 0)) & (DSP_FAULT_MASK | DSP_ACKSTAT_MASK)) == 0
    )
    if not live:
        return None
    expected = golden_images.get(unit, {}).get(preset)
    if expected is None:
        return None
    observed = bytes.fromhex(image_hex)
    if observed == expected:
        return None

    diffs = _image_diff(expected, observed)
    around = sorted(
        {
            max(TAS_BIQUAD_FIRST, d["subaddr"] + delta)
            for d in diffs[:4]
            for delta in (-1, 0, 1)
            if TAS_BIQUAD_FIRST <= d["subaddr"] + delta <= TAS_BIQUAD_LAST
        }
    )
    tas_near = {f"0x{sub:02X}": _tas_write_tail(chain, unit, sub) for sub in around}
    observed_payload = {
        "unit": unit,
        "reported_preset": "B" if preset else "A",
        "expected_digest": _digest_bytes(expected),
        "observed_digest": _digest_bytes(observed),
        "diffs": diffs[:16],
        "diff_count": len(diffs),
        "active_flags": active_flags,
        "preset_job_state": int(unit_state.get("preset_job_state", 0)),
        "preset_job_index": int(unit_state.get("preset_job_index", 0)),
        "preset_job_target": int(unit_state.get("preset_job_target", 0)),
        "preset_job_flags": int(unit_state.get("preset_job_flags", 0)),
        "dsp_fault_flags": int(unit_state.get("dsp_fault_flags", 0)),
        "src_live_pcm": src_live_pcm,
        "latest_tas30": str(unit_state.get("tas30_last_write", "")),
        "tas30_write_count": int(unit_state.get("tas30_write_count", 0)),
        "tas_near_diff_writes": tas_near,
        "src_regs": unit_state.get("src_regs", {}),
        "src_stats": unit_state.get("src_stats", {}),
        "tas_stats": unit_state.get("tas_stats", {}),
        "lcd": sample.get("lcd"),
        "recent_stimuli": recent_events or [],
    }
    return Incident(
        "HIGH",
        "audio.golden_coeff.live_wrong_image",
        (
            f"MAIN{unit} is live on preset {'B' if preset else 'A'} "
            "with DSP coefficients different from the clean golden image"
        ),
        (
            "a settled, unmuted, fault-free MAIN must never restore live audio "
            "unless its DSP preset coefficients match the reported preset"
        ),
        observed_payload,
        "MAIN preset APPLY / TAS3108 coefficient image",
        (
            "live-wrong-coeff:"
            f"unit{unit}:preset{preset}:"
            f"{observed_payload['expected_digest']}:{observed_payload['observed_digest']}"
        ),
    )


def _golden_match_fields(
    unit_state: dict[str, Any],
    golden_images: dict[int, dict[int, bytes]] | None,
) -> dict[str, Any]:
    if not golden_images:
        return {}
    unit = int(unit_state["unit"])
    preset = int(unit_state["active_preset"])
    expected = golden_images.get(unit, {}).get(preset)
    image_hex = str(unit_state.get("dsp_biquad_image", ""))
    if expected is None or not image_hex:
        return {}
    observed = bytes.fromhex(image_hex)
    active_flags = int(unit_state["active_flags"])
    src_live_pcm = _src_regs_indicate_live_pcm(unit_state)
    live_checked = (
        int(unit_state.get("preset_job_state", 0)) == 0
        and bool(active_flags & MAIN_ACTIVE_GATE_MASK)
        and not bool(active_flags & MAIN_ACTIVE_MUTE_MASK)
        and src_live_pcm
        and _int_from_hex(str(unit_state.get("tas30_last_write", ""))) != 0
        and (int(unit_state.get("dsp_fault_flags", 0)) & (DSP_FAULT_MASK | DSP_ACKSTAT_MASK)) == 0
    )
    return {
        "golden_coeff_digest": _digest_bytes(expected),
        "golden_coeff_match": observed == expected,
        "golden_coeff_live_checked": live_checked,
        "golden_coeff_src_live_pcm": src_live_pcm,
    }


def build_preset_phase_sweep_plan(
    rng: random.Random,
    *,
    cycles: int = 2,
    sample_count: int = PHASE_SAMPLE_COUNT,
) -> list[tuple[str, dict[str, Any]]]:
    plan: list[tuple[str, dict[str, Any]]] = []
    start_b_to_a = bool(rng.randrange(2))
    for cycle in range(cycles):
        b_to_a = start_b_to_a if cycle % 2 == 0 else not start_b_to_a
        origin_b = b_to_a
        target_b = not origin_b
        delay = rng.choice(PHASE_SWEEP_DELAYS) + rng.randrange(PHASE_SWEEP_JITTER)
        use_churn = bool(rng.randrange(2))
        direction = ("B" if origin_b else "A") + "->" + ("B" if target_b else "A")
        origin_setup: list[tuple[str, dict[str, Any]]] = []
        if not origin_b:
            origin_setup.extend(
                [
                    (
                        "ir",
                        {
                            "cmd": IR_CMDS["preset_b"],
                            "settle_ticks": 0,
                            "purpose": "phase_origin_primer",
                            "direction": direction,
                            "observe": False,
                        },
                    ),
                    (
                        "step",
                        {
                            "ticks": 160_000_000,
                            "purpose": "phase_origin_primer_settle",
                            "direction": direction,
                            "observe": False,
                        },
                    ),
                ]
            )
        origin_setup.extend(
            [
                (
                    "ir",
                    {
                        "cmd": IR_CMDS["preset_b"] if origin_b else IR_CMDS["preset_a"],
                        "settle_ticks": 0,
                        "purpose": "phase_origin",
                        "direction": direction,
                        "observe": False,
                    },
                ),
                (
                    "step",
                    {
                        "ticks": 160_000_000,
                        "purpose": "phase_origin_settle",
                        "direction": direction,
                        "observe": False,
                    },
                ),
            ]
        )
        plan.extend(origin_setup)
        if use_churn:
            plan.append(
                (
                    "src_rxckr_hole",
                    {
                        "units": [0, 1],
                        "purpose": "phase_src_churn",
                        "direction": direction,
                    },
                )
            )
        plan.extend(
            [
                (
                    "step",
                    {
                        "ticks": delay,
                        "purpose": "phase_delay_before_second",
                        "phase_delay_ticks": delay,
                        "direction": direction,
                        "src_rxckr_churn": use_churn,
                    },
                ),
                (
                    "ir",
                    {
                        "cmd": IR_CMDS["preset_b"] if target_b else IR_CMDS["preset_a"],
                        "settle_ticks": 0,
                        "purpose": "phase_target",
                        "direction": direction,
                        "phase_delay_ticks": delay,
                        "src_rxckr_churn": use_churn,
                        "observe": False,
                    },
                ),
            ]
        )
        if use_churn:
            plan.append(
                (
                    "src_rxckr_locked",
                    {
                        "units": [0, 1],
                        "purpose": "phase_src_restore",
                        "direction": direction,
                    },
                )
            )
        plan.append(
            (
                "phase_sample_window",
                {
                    "ticks": PHASE_SAMPLE_TICKS,
                    "samples": sample_count,
                    "purpose": "phase_apply_commit_sample",
                    "direction": direction,
                    "phase_delay_ticks": delay,
                    "src_rxckr_churn": use_churn,
                },
            )
        )
    return plan


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
        self.golden_images = learn_preset_golden_images(self.control_hex, self.main_hex)
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
            "golden_coefficients": _golden_summary(self.golden_images),
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
            ("preset-phase-sweep", 12),
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
        src_initial = self.rng.choice(["locked", "lost", "non_pcm", "flap"])
        if campaign == "preset-phase-sweep":
            src_initial = "locked"
        return SessionConfig(
            session_id=session_id,
            campaign=campaign,
            seed=self.rng.getrandbits(64),
            slot_a_pb1=a,
            slot_b_pb1=b,
            slot_a_pb2=a2,
            slot_b_pb2=b2,
            src_initial=src_initial,
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
        cursor_map = getattr(self, "_dsp30_cursor", {0: 0, 1: 0})
        main_diag = []
        for unit in (0, 1):
            tas30_all = chain.read_main_dsp_write_payloads(unit, TAS_VOLUME_SUBADDR)
            tas30_cursor = cursor_map.get(unit, 0)
            tas30_since = tas30_all[tas30_cursor:]
            cursor_map[unit] = len(tas30_all)
            active_flags = chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS)
            biquad_image = _dsp_biquad_image(chain, unit)
            full_image = bytes(chain.read_main_dsp_reg(unit, s) for s in range(0x00, 0x100))
            unit_state = {
                "unit": unit,
                "active_flags": active_flags,
                "active_preset": (active_flags & MAIN_ACTIVE_PRESET_MASK) >> 2,
                "active_gate": (active_flags & MAIN_ACTIVE_GATE_MASK) >> 3,
                "active_mute": (active_flags & MAIN_ACTIVE_MUTE_MASK) >> 4,
                "preset_job_state": chain.read_main_reg(unit, MAIN_PRESET_JOB_STATE),
                "preset_job_target": chain.read_main_reg(unit, MAIN_PRESET_JOB_TARGET),
                "preset_job_index": chain.read_main_reg(unit, MAIN_PRESET_JOB_INDEX),
                "preset_job_flags": chain.read_main_reg(unit, MAIN_PRESET_JOB_FLAGS),
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
                "tas30_last_write": (tas30_all[-1].hex() if tas30_all else ""),
                "tas30_write_count": len(tas30_all),
                # 0x30 writes since the previous sample (display-capped), so a
                # transient unmute-while-muted is visible to the oracle.
                "tas30_writes_since": [p.hex() for p in tas30_since[-16:]],
                # UNCAPPED leak signal: did ANY non-zero (unmute) 0x30 write
                # happen this interval?  Survives the display cap above, so a
                # bursty interval cannot hide the transient.
                "tas30_nonzero_since": any(int.from_bytes(p, "big") for p in tas30_since),
                # ACTUAL DSP preset-coefficient image.  The biquad range
                # 0x37..0x90 is the preset-defining coefficient block; it
                # excludes volume so it changes on preset switch but not volume.
                "dsp_biquad_image": biquad_image.hex(),
                "dsp_biquad_digest": _digest_bytes(biquad_image),
                "dsp_full_digest": _digest_bytes(full_image),
                "src_regs": {
                    f"0x{reg:02X}": chain.read_main_src4382_reg(unit, reg)
                    for reg in (SRC_REG_NON_PCM, SRC_REG_RX_STATUS, SRC_REG_RX_LOCK)
                },
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
            unit_state.update(_golden_match_fields(unit_state, self.golden_images))
            main_diag.append(
                unit_state
            )
        lcd = chain.lcd_lines()
        sample = {
            "kind": kind,
            "session_id": session_id,
            "campaign": config.campaign,
            # Monotonic per-run sequence number: the causal write order, robust
            # even if a future regression makes `tick` non-monotonic again
            # (mid-session resets used to rewind the universal clock, which
            # scrambled tick-sorted timeline merges downstream).
            "obs_seq": self.stats.observations,
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
            golden_incident = _golden_coeff_incident(
                sample,
                unit_state,
                self.golden_images,
                chain=chain,
                recent_events=list(self.recent_events),
            )
            if golden_incident is not None:
                incidents.append(golden_incident)
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
        if action == "src_rxckr_hole":
            for unit in params.get("units", [0, 1]):
                _set_src_regs(chain, int(unit), SRC_RXCKR_HOLE_REGS)
            chain.step_ticks(int(params.get("settle_ticks", 0)))
            return
        if action == "src_rxckr_locked":
            for unit in params.get("units", [0, 1]):
                _set_src_regs(chain, int(unit), SRC_LOCKED_REGS)
            chain.step_ticks(int(params.get("settle_ticks", 0)))
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
        if campaign == "preset-phase-sweep":
            first_b = bool(self.rng.randrange(2))
            return (
                "ir",
                {
                    "cmd": IR_CMDS["preset_b"] if first_b else IR_CMDS["preset_a"],
                    "settle_ticks": 0,
                    "purpose": "phase-fallback",
                },
            )
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

    def _observe(
        self,
        chain: Chain,
        config: SessionConfig,
        previous: dict[str, Any] | None,
    ) -> dict[str, Any]:
        sample = self._sample(chain, config.session_id, config, kind="observation")
        for incident in self._oracles(chain, config.session_id, config, sample, previous):
            self._record_incident(chain, config.session_id, config, incident)
        self._status(force=False)
        return sample

    def _run_preset_phase_sweep(
        self,
        chain: Chain,
        config: SessionConfig,
        previous: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        cycles = self.rng.choice([1, 2])
        plan = build_preset_phase_sweep_plan(self.rng, cycles=cycles)
        for action, params in plan:
            if time.monotonic() >= self.deadline:
                break
            if action == "phase_sample_window":
                samples = int(params["samples"])
                ticks = int(params["ticks"])
                for idx in range(samples):
                    if time.monotonic() >= self.deadline:
                        break
                    step_params = {
                        "ticks": ticks,
                        "purpose": params.get("purpose", "phase_sample"),
                        "sample_index": idx,
                        "samples": samples,
                        "direction": params.get("direction"),
                        "phase_delay_ticks": params.get("phase_delay_ticks"),
                        "src_rxckr_churn": params.get("src_rxckr_churn", False),
                    }
                    self._safe_action(chain, config, "step", step_params)
                    previous = self._observe(chain, config, previous)
                continue
            self._safe_action(chain, config, action, params)
            if params.get("observe", True):
                previous = self._observe(chain, config, previous)
        return previous

    def _run_session(self, config: SessionConfig) -> None:
        chain = self._new_chain(config)
        # per-unit cursor into each DSP's TAS 0x30 write log, so each sample can
        # report the volume-coefficient writes SINCE the previous sample (a
        # non-zero write while muted must not be hidden by a later zero write).
        self._dsp30_cursor = {0: 0, 1: 0}
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
            if config.campaign == "preset-phase-sweep":
                self._run_preset_phase_sweep(chain, config, previous)
                return
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
                previous = self._observe(chain, config, previous)
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
    parser.add_argument("--main-hex", default=str(V35_MAIN_HEX))
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
