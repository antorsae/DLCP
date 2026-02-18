#!/usr/bin/env python3
"""
Simulation framework orchestrator.

Examples:
  python3 scripts/simctl.py overlay-check
  python3 scripts/simctl.py gpsim-lcd --cycles 50000000
  python3 scripts/simctl.py main-gpsim --timer-model harness --frames 0xB0:0x20:0x01 --stage1-timeout 60
  python3 scripts/simctl.py compare-timer3 --frames 0xB0:0x20:0x01
  python3 scripts/simctl.py run-exhaustive
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dlcp_fw.sim.gpsim import GpsimRunConfig, run_gpsim
from dlcp_fw.sim.lcd import LcdState, decode_lcd_bytes
from dlcp_fw.sim.main_gpsim import run_main_mailbox_gpsim
from dlcp_fw.sim.main_gpsim_timer3 import compare_timer3_models, run_main_mailbox_gpsim_harness_timer3
from dlcp_fw.sim.manifests import control_disable_boot_wait, control_reset_to_appstart
from dlcp_fw.sim.overlay import apply_overlays
from dlcp_fw.sim.paths import ANALYSIS_ROOT, CONTROL_HEX_PATCHED, SIM_ARTIFACTS_DIR
from dlcp_fw.sim.protocol import SerialFrame
from dlcp_fw.sim.scenarios import run_fault_matrix, run_preset_ab_roundtrip


def cmd_overlay_check() -> int:
    with tempfile.TemporaryDirectory(prefix="sim_overlay_check_") as td:
        out_hex = Path(td) / "control_sim.hex"
        res = apply_overlays(
            CONTROL_HEX_PATCHED,
            out_hex,
            manifests=[control_reset_to_appstart()],
        )
        summary = {r.manifest_name: r.changed_bytes for r in res}
        print("overlay-check: OK")
        print("output:", out_hex)
        print("changed:", json.dumps(summary, sort_keys=True))
    return 0


def cmd_gpsim_lcd(cycles: int, fast: bool, keep: bool) -> int:
    manifests = [control_reset_to_appstart()]
    if fast:
        manifests.append(control_disable_boot_wait())

    tmp_base = Path(tempfile.mkdtemp(prefix="sim_gpsim_lcd_"))
    try:
        sim_hex = tmp_base / "control_sim.hex"
        apply_overlays(CONTROL_HEX_PATCHED, sim_hex, manifests=manifests)
        run_dir = tmp_base / "gpsim"
        result = run_gpsim(
            GpsimRunConfig(
                hex_path=sim_hex,
                cycles=cycles,
            ),
            run_dir,
        )
        lcd_bytes = decode_lcd_bytes(result.log_path)
        st = LcdState.new()
        for b in lcd_bytes:
            st.apply(b)
        print("gpsim-lcd: OK")
        print("hex:", sim_hex)
        print("decoded-bytes:", len(lcd_bytes))
        print(f"|{st.line1()}|")
        print(f"|{st.line2()}|")
        print("artifacts:", run_dir)
        if keep:
            keep_dir = SIM_ARTIFACTS_DIR / "gpsim_lcd_last"
            keep_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sim_hex, keep_dir / "sim.hex")
            shutil.copy2(result.log_path, keep_dir / "gpsim.log")
            shutil.copy2(result.cli_path, keep_dir / "gpsim_cli.txt")
            print("saved:", keep_dir)
        return 0
    finally:
        if not keep:
            shutil.rmtree(tmp_base, ignore_errors=True)


def cmd_run_exhaustive(pytest_cmd: str) -> int:
    roundtrip = run_preset_ab_roundtrip()
    faults = run_fault_matrix()
    print("scenario-roundtrip:")
    print(
        json.dumps(
            {
                "control_frames": roundtrip.control_frames,
                "bus_events": roundtrip.bus_events,
                "left_apply": roundtrip.left_apply,
                "right_apply": roundtrip.right_apply,
                "digest_a": roundtrip.digest_a[:16],
                "digest_b": roundtrip.digest_b[:16],
            },
            sort_keys=True,
        )
    )
    print("fault-matrix:", json.dumps(faults, sort_keys=True))

    if pytest_cmd == "auto":
        venv_pytest = ANALYSIS_ROOT / ".venv_ep0" / "bin" / "pytest"
        pytest_cmd = str(venv_pytest) if venv_pytest.exists() else "pytest"
    cmd = [pytest_cmd, "-q", "tests/sim"]
    cp = subprocess.run(cmd, cwd=ANALYSIS_ROOT)
    return cp.returncode


def _parse_frames_arg(text: str) -> list[SerialFrame]:
    out: list[SerialFrame] = []
    for tok in [x.strip() for x in text.split(",") if x.strip()]:
        parts = tok.split(":")
        if len(parts) != 3:
            raise SystemExit(f"invalid frame token {tok!r}, expected route:cmd:data")
        route, cmd, data = (int(p, 0) & 0xFF for p in parts)
        out.append(SerialFrame(route=route, cmd=cmd, data=data))
    if not out:
        raise SystemExit("no frames parsed")
    return out


def cmd_main_gpsim(
    frames_arg: str,
    cycles: int,
    parser_break: int,
    stage1_timeout: float,
    timer_model: str,
    gpasm: str,
    keep: bool,
) -> int:
    frames = _parse_frames_arg(frames_arg)
    timer_events = None
    if timer_model == "semantic":
        res = run_main_mailbox_gpsim(
            frames=frames,
            cycles=cycles,
            parser_break_addr=parser_break,
            stage1_timeout_s=stage1_timeout,
            gpasm=gpasm,
            keep_artifacts=keep,
        )
    elif timer_model == "harness":
        harness_res = run_main_mailbox_gpsim_harness_timer3(
            frames=frames,
            cycles=cycles,
            parser_break_addr=parser_break,
            stage1_timeout_s=stage1_timeout,
            gpasm=gpasm,
            keep_artifacts=keep,
        )
        res = harness_res.run
        timer_events = harness_res.timer3_events
        mailbox_consumed = harness_res.mailbox_consumed
    else:
        raise SystemExit(f"unknown timer model: {timer_model}")

    reg5e = res.regs.get(0x5E, 0)
    rx_rd = res.regs.get(0x7C0, 0)
    rx_wr = res.regs.get(0x7C1, 0)
    tx_wr = res.regs.get(0x7C3, 0)
    print("main-gpsim: OK")
    print("timer-model:", timer_model)
    print("frames:", [str(f) for f in frames])
    print("tx-bytes:", [f"0x{x:02X}" for x in res.tx_bytes[:48]])
    print(f"parser-break-hit: {int(res.parser_break_hit)}")
    print(f"REG 0x05E: 0x{reg5e:02X}")
    print(f"mailbox: rx_rd={rx_rd} rx_wr={rx_wr} tx_wr={tx_wr}")
    if timer_events is not None:
        print("timer3-events:", len(timer_events))
        print("mailbox-consumed:", int(mailbox_consumed))
        if timer_events:
            avg = sum(e.overflow_cycles for e in timer_events) / len(timer_events)
            print(f"timer3-overflow-cycles-avg: {avg:.1f}")
    if keep:
        print("artifacts:", res.log_path.parent)
    return 0


def cmd_compare_timer3(
    frames_arg: str,
    cycles: int,
    stage1_timeout: float,
    gpasm: str,
) -> int:
    frames = _parse_frames_arg(frames_arg)
    cmp_res = compare_timer3_models(
        frames=frames,
        cycles=cycles,
        stage1_timeout_s=stage1_timeout,
        gpasm=gpasm,
    )
    s = cmp_res.semantic
    h = cmp_res.harness.run
    print("compare-timer3: OK")
    print("frames:", [str(f) for f in frames])
    print(
        "semantic:",
        {
            "parser": int(s.parser_break_hit),
            "reg5e": f"0x{s.regs.get(0x5E, 0):02X}",
            "rx_rd": s.regs.get(0x7C0, 0),
            "rx_wr": s.regs.get(0x7C1, 0),
            "tx_wr": s.regs.get(0x7C3, 0),
            "tx_len": len(s.tx_bytes),
        },
    )
    print(
        "harness:",
        {
            "parser": int(h.parser_break_hit),
            "reg5e": f"0x{h.regs.get(0x5E, 0):02X}",
            "rx_rd": h.regs.get(0x7C0, 0),
            "rx_wr": h.regs.get(0x7C1, 0),
            "tx_wr": h.regs.get(0x7C3, 0),
            "tx_len": len(h.tx_bytes),
            "timer3_events": len(cmp_res.harness.timer3_events),
            "mailbox_consumed": int(cmp_res.harness.mailbox_consumed),
        },
    )
    print("same-reg5e:", int(cmp_res.same_reg5e))
    print("same-mailbox:", int(cmp_res.same_mailbox_counters))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("overlay-check", help="validate simulation overlay generation")

    p_lcd = sub.add_parser("gpsim-lcd", help="run gpsim and decode LCD using sim overlays")
    p_lcd.add_argument("--cycles", type=int, default=50_000_000)
    p_lcd.add_argument("--fast", action="store_true", help="apply optional delay-bypass overlay")
    p_lcd.add_argument("--keep", action="store_true", help="keep temp and save artifacts")

    p_ex = sub.add_parser("run-exhaustive", help="run scenario checks + full sim pytest suite")
    p_ex.add_argument(
        "--pytest-cmd",
        default="auto",
        help="pytest executable path, or 'auto' to use .venv_ep0/bin/pytest when available",
    )

    p_main = sub.add_parser("main-gpsim", help="run instruction-level main dispatch via mailbox hooks")
    p_main.add_argument(
        "--frames",
        default="0xB0:0x20:0x01",
        help="comma-separated route:cmd:data triples (ints, accepts 0xNN)",
    )
    p_main.add_argument("--cycles", type=int, default=120_000_000)
    p_main.add_argument("--parser-break", type=lambda s: int(s, 0), default=0x1BEA)
    p_main.add_argument("--stage1-timeout", type=float, default=60.0)
    p_main.add_argument("--timer-model", choices=["semantic", "harness"], default="semantic")
    p_main.add_argument("--gpasm", default="gpasm")
    p_main.add_argument("--keep", action="store_true", help="keep artifacts under artifacts/sim/current/")

    p_cmp = sub.add_parser("compare-timer3", help="compare semantic Timer3 shim vs harness Timer3 model")
    p_cmp.add_argument(
        "--frames",
        default="0xB0:0x20:0x01",
        help="comma-separated route:cmd:data triples (ints, accepts 0xNN)",
    )
    p_cmp.add_argument("--cycles", type=int, default=120_000_000)
    p_cmp.add_argument("--stage1-timeout", type=float, default=60.0)
    p_cmp.add_argument("--gpasm", default="gpasm")

    args = ap.parse_args()
    if args.cmd == "overlay-check":
        return cmd_overlay_check()
    if args.cmd == "gpsim-lcd":
        return cmd_gpsim_lcd(cycles=args.cycles, fast=args.fast, keep=args.keep)
    if args.cmd == "run-exhaustive":
        return cmd_run_exhaustive(pytest_cmd=args.pytest_cmd)
    if args.cmd == "main-gpsim":
        return cmd_main_gpsim(
            frames_arg=args.frames,
            cycles=args.cycles,
            parser_break=args.parser_break,
            stage1_timeout=args.stage1_timeout,
            timer_model=args.timer_model,
            gpasm=args.gpasm,
            keep=args.keep,
        )
    if args.cmd == "compare-timer3":
        return cmd_compare_timer3(
            frames_arg=args.frames,
            cycles=args.cycles,
            stage1_timeout=args.stage1_timeout,
            gpasm=args.gpasm,
        )
    raise SystemExit(f"unknown command {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
