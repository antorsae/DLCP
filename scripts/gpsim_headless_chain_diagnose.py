#!/usr/bin/env python3
"""
Headless gpsim chain diagnoser for DLCP CONTROL + MAIN(s).

Supports 1-main (terminated) and 2-main (daisy-chain) topologies.

Produces a JSON timeline focused on:
- CONTROL standby state bit transitions (flags 0x1F bit1)
- protocol TX frames (CONTROL/MAIN0/MAIN1)
- mailbox counters and link overrun statistics
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from collections import Counter, deque
from pathlib import Path
from typing import Deque, Dict, List

import _bootstrap

from gpsim_tui_simulator import (
    CONTROL_FOSC_HZ,
    MAIN_FOSC_HZ,
    GpsimControlSession,
    LinkPipe,
    MainGpsimSession,
    MainMemSnapshot,
    MemSnapshot,
    TxTriplet,
    _byte_cycles,
)
from dlcp_fw.paths import SIM_ARTIFACTS_DIR

ROOT = _bootstrap.REPO_ROOT


def _parse_adc12(text: str) -> int:
    try:
        value = int(text, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ADC value: {text!r}") from exc
    if value < 0 or value > 0x0FFF:
        raise argparse.ArgumentTypeError("ADC value must be in range 0x000..0xFFF")
    return value


def _frame_dict(f: TxTriplet, src: str) -> Dict[str, int | str]:
    return {
        "src": src,
        "cycle": int(f.cycle),
        "route": int(f.route),
        "cmd": int(f.cmd),
        "data": int(f.data),
    }


def _control_rc1_level(mem: MemSnapshot) -> int:
    if (mem.trisc & 0x02) == 0:
        return 1 if (mem.latc & 0x02) else 0
    return 1 if (mem.portc & 0x02) else 0


_DUMMY_MAIN_SNAPSHOT = MainMemSnapshot(
    cycle=0, status_5e=0, flags_7e=0, parser_98=0, flags_94=0,
    cmd_a2=0, data_a3=0, link_c3=0, adcon0=0, adresh=0, adresl=0,
    input_99=0, vol_cur=(0, 0, 0, 0), vol_tgt=(0, 0, 0, 0),
    ch_cfg_cur=(0, 0, 0, 0, 0, 0), ch_cfg_shadow=(0, 0, 0, 0, 0, 0),
    mb_rd=0, mb_wr=0, mb_tx_wr=0, portc=0, trisc=0,
)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("control_hex", type=Path, help="CONTROL firmware HEX path")
    ap.add_argument(
        "--main-hex", action="append", type=Path, required=True,
        help="MAIN firmware HEX path (pass once to reuse for both, or twice for #0/#1)",
    )
    ap.add_argument("--gpasm", default="gpasm", help="gpasm executable")
    ap.add_argument("--duration-s", type=float, default=60.0,
                    help="measurement duration in simulated seconds")
    ap.add_argument(
        "--control-ips", type=float, default=3_000_000.0,
        help="CONTROL instruction cycles per second (default 3 MHz for 12 MHz osc)",
    )
    ap.add_argument("--warmup-cycles", type=int, default=20_000_000,
                    help="warmup cycles before measurement")
    ap.add_argument("--chunk-cycles", type=int, default=300_000,
                    help="CONTROL cycles per step")
    ap.add_argument("--main-chunk-cycles", type=int, default=300_000,
                    help="MAIN cycles per step")
    ap.add_argument(
        "--main0-standby", choices=("control", "auto", "hold", "release"),
        default="hold", help="MAIN #0 standby AN0 model",
    )
    ap.add_argument(
        "--main1-standby", choices=("control", "auto", "hold", "release"),
        default="hold", help="MAIN #1 standby AN0 model",
    )
    ap.add_argument(
        "--main-ra0", type=_parse_adc12, default=0x0228,
        help="force MAIN AN0 ADC sample on both units (0x000..0xFFF)",
    )
    ap.add_argument(
        "--main0-rc2", choices=("high", "low", "keep"), default="high",
        help="MAIN #0 RC2 strap model",
    )
    ap.add_argument(
        "--main1-rc2", choices=("high", "low", "keep"), default="low",
        help="MAIN #1 RC2 strap model",
    )
    ap.add_argument(
        "--main-timer3", choices=("shim", "harness"), default="shim",
        help="MAIN Timer3 mode",
    )
    ap.add_argument("--fast-boot", action="store_true",
                    help="apply optional CONTROL startup delay bypass")
    ap.add_argument("--hold-cycles", type=int, default=240_000,
                    help="key hold width (unused in headless run)")
    ap.add_argument("--sample-every-cycles", type=int, default=3_000_000,
                    help="periodic snapshot cadence during measurement")
    ap.add_argument("--recent-frame-window", type=int, default=200,
                    help="number of recent frames retained around a bit transition")
    ap.add_argument("--event-cycle-window", type=int, default=1_500_000,
                    help="cycle window around each bit transition to include frames")
    ap.add_argument(
        "--single-main", action="store_true",
        help="run with only one MAIN unit (terminated chain end)",
    )
    ap.add_argument(
        "--rx-fifo-limit", type=int, default=47,
        help="max bytes in RX mailbox before overrun (default 47 = CONTROL ring capacity)",
    )
    ap.add_argument(
        "--output", type=Path,
        default=SIM_ARTIFACTS_DIR / "headless_chain_diagnose.json",
        help="output JSON path",
    )
    return ap.parse_args()


def _main_hex_pair(hexes: List[Path]) -> List[Path]:
    if len(hexes) == 1:
        return [hexes[0], hexes[0]]
    if len(hexes) == 2:
        return [hexes[0], hexes[1]]
    raise SystemExit("Pass --main-hex once or twice")


def main() -> int:
    args = parse_args()
    if not args.control_hex.exists():
        raise SystemExit(f"CONTROL HEX not found: {args.control_hex}")
    for p in args.main_hex:
        if not p.exists():
            raise SystemExit(f"MAIN HEX not found: {p}")
    if shutil.which(args.gpasm) is None:
        raise SystemExit(f"gpasm not found: {args.gpasm}")

    main_hexes = _main_hex_pair(args.main_hex)
    single_main = args.single_main
    measure_cycles = int(args.duration_s * args.control_ips)
    target_cycles = args.warmup_cycles + max(1, measure_cycles)

    control = GpsimControlSession(
        args.control_hex,
        fast_boot=args.fast_boot,
        chunk_cycles=args.chunk_cycles,
        hold_cycles=args.hold_cycles,
        rx_fifo_limit=args.rx_fifo_limit,
    )
    main0 = MainGpsimSession(
        main_hexes[0],
        gpasm=args.gpasm,
        chunk_cycles=args.main_chunk_cycles,
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
            chunk_cycles=args.main_chunk_cycles,
            tag="1",
            standby_mode=args.main1_standby,
            main_ra0_adc=args.main_ra0,
            rc2_mode=args.main1_rc2,
            timer3_mode=args.main_timer3,
            rx_fifo_limit=args.rx_fifo_limit,
        )
    )

    # Byte-paced links (PIC18F2550 EUSART: 2-byte RCREG, no flow control).
    ctl_byte_cyc = _byte_cycles(CONTROL_FOSC_HZ)
    main_byte_cyc = _byte_cycles(MAIN_FOSC_HZ)
    fifo = args.rx_fifo_limit

    link_ctl_m0 = LinkPipe("CTL->M0", byte_cycles=ctl_byte_cyc, fifo_depth=fifo)
    link_m0_ctl = LinkPipe("M0->CTL", byte_cycles=main_byte_cyc, fifo_depth=fifo)
    if single_main:
        link_m0_m1 = None
        link_m1_m0 = None
        all_links = [link_ctl_m0, link_m0_ctl]
    else:
        link_m0_m1 = LinkPipe("M0->M1", byte_cycles=main_byte_cyc, fifo_depth=fifo)
        link_m1_m0 = LinkPipe("M1->M0", byte_cycles=main_byte_cyc, fifo_depth=fifo)
        all_links = [link_ctl_m0, link_m0_ctl, link_m0_m1, link_m1_m0]

    def pump_pre_control(now_cycle: int) -> Dict[str, int]:
        d: Dict[str, int] = {
            "m02c": link_m0_ctl.pump(now_cycle, control),
        }
        if link_m1_m0 is not None:
            d["m12m0"] = link_m1_m0.pump(now_cycle, main0)
        return d

    def pump_pre_main0(now_cycle: int) -> Dict[str, int]:
        return {"c2m0": link_ctl_m0.pump(now_cycle, main0)}

    def pump_pre_main1(now_cycle: int) -> Dict[str, int]:
        d: Dict[str, int] = {}
        if link_m0_m1 is not None and main1 is not None:
            d["m02m1"] = link_m0_m1.pump(now_cycle, main1)
        d["m02c"] = link_m0_ctl.pump(now_cycle, control)
        return d

    def pump_post_main1(now_cycle: int) -> Dict[str, int]:
        if link_m1_m0 is not None:
            return {"m12m0": link_m1_m0.pump(now_cycle, main0)}
        return {}

    def enqueue_control_tx(frames: List[TxTriplet]) -> None:
        for f in frames:
            if (f.route & 0xF0) == 0xB0:
                link_ctl_m0.enqueue(f)

    def enqueue_main0_tx(frames: List[TxTriplet]) -> None:
        for f in frames:
            if single_main:
                # Ring topology: MAIN0 TX → CONTROL RX (all frames)
                link_m0_ctl.enqueue(f)
            elif f.route == 0xBF:
                link_m0_ctl.enqueue(f)
            elif (f.route & 0xF0) == 0xB0 and link_m0_m1 is not None:
                link_m0_m1.enqueue(f)

    def enqueue_main1_tx(frames: List[TxTriplet]) -> None:
        for f in frames:
            if f.route == 0xBF and link_m1_m0 is not None:
                link_m1_m0.enqueue(f)

    all_tx: List[Dict[str, int | str]] = []
    bit1_events: List[Dict[str, object]] = []
    snapshots: List[Dict[str, object]] = []
    recent_frames: Deque[Dict[str, int | str]] = deque(
        maxlen=max(32, args.recent_frame_window)
    )

    t0 = time.monotonic()

    def _progress(label: str, cycle: int) -> None:
        elapsed = time.monotonic() - t0
        pct = 100.0 * cycle / target_cycles if target_cycles else 0
        sys.stderr.write(
            f"\r{label} cycle=0x{cycle:08X} ({pct:5.1f}%)  "
            f"elapsed={elapsed:.1f}s  "
            f"oerr c2m0={link_ctl_m0.overrun_total} m02c={link_m0_ctl.overrun_total}"
        )
        sys.stderr.flush()

    try:
        # Warmup
        lcd_lines = (" " * 16, " " * 16)
        ctl_mem = control.read_mem_snapshot()
        main_mem0, _ = main0.step()
        main_mem1 = _DUMMY_MAIN_SNAPSHOT
        if main1 is not None:
            main_mem1, _ = main1.step()

        while control.current_cycle < args.warmup_cycles:
            pump_pre_control(control.current_cycle)
            lcd_lines, ctl_mem, ctl_tx, ctl_cycle = control.step()
            for f in ctl_tx:
                d = _frame_dict(f, "CTL_TX")
                all_tx.append(d)
                recent_frames.append(d)
            enqueue_control_tx(ctl_tx)
            pump_pre_main0(ctl_cycle)
            standby_bus = _control_rc1_level(ctl_mem)
            main0.set_standby_bus(standby_bus)
            main_mem0, main_tx0 = main0.step()
            for f in main_tx0:
                src = "M0_TX_TO_CTL" if f.route == 0xBF else "M0_TX_TO_M1"
                d = _frame_dict(f, src)
                all_tx.append(d)
                recent_frames.append(d)
            enqueue_main0_tx(main_tx0)
            pump_pre_main1(ctl_cycle)
            if main1 is not None:
                main1.set_standby_bus(standby_bus)
                main_mem1, main_tx1 = main1.step()
                for f in main_tx1:
                    src = "M1_TX_TO_M0" if f.route == 0xBF else "M1_TX_OTHER"
                    d = _frame_dict(f, src)
                    all_tx.append(d)
                    recent_frames.append(d)
                enqueue_main1_tx(main_tx1)
            pump_post_main1(ctl_cycle)
            if control.current_cycle % 3_000_000 < args.chunk_cycles:
                _progress("warmup", control.current_cycle)

        bit1_prev = (ctl_mem.flags >> 1) & 1
        last_sample_cycle = control.current_cycle
        sys.stderr.write("\n")
        print(
            f"warmup done  cycle=0x{control.current_cycle:08X}  "
            f"lcd='{lcd_lines[0].rstrip()}'/{lcd_lines[1].rstrip()}'  "
            f"bit1={bit1_prev}  flags=0x{ctl_mem.flags:02X}"
        )

        # Measurement
        while control.current_cycle < target_cycles:
            pre_cycle = control.current_cycle
            pump_pre_control(pre_cycle)

            lcd_lines, ctl_mem, ctl_tx, ctl_cycle = control.step()
            for f in ctl_tx:
                d = _frame_dict(f, "CTL_TX")
                all_tx.append(d)
                recent_frames.append(d)
            enqueue_control_tx(ctl_tx)
            pump_pre_main0(ctl_cycle)

            standby_bus = _control_rc1_level(ctl_mem)
            main0.set_standby_bus(standby_bus)

            main_mem0, main_tx0 = main0.step()
            for f in main_tx0:
                src = "M0_TX_TO_CTL" if f.route == 0xBF else "M0_TX_TO_M1"
                d = _frame_dict(f, src)
                all_tx.append(d)
                recent_frames.append(d)
            enqueue_main0_tx(main_tx0)
            pump_pre_main1(ctl_cycle)

            if main1 is not None:
                main1.set_standby_bus(standby_bus)
                main_mem1, main_tx1 = main1.step()
                for f in main_tx1:
                    src = "M1_TX_TO_M0" if f.route == 0xBF else "M1_TX_OTHER"
                    d = _frame_dict(f, src)
                    all_tx.append(d)
                    recent_frames.append(d)
                enqueue_main1_tx(main_tx1)
            pump_post_main1(ctl_cycle)

            bit1_now = (ctl_mem.flags >> 1) & 1
            if bit1_now != bit1_prev:
                win = [
                    f for f in list(recent_frames)
                    if abs(int(f["cycle"]) - int(ctl_cycle)) <= int(args.event_cycle_window)
                ]
                ev: Dict[str, object] = {
                    "ctl_cycle": int(ctl_cycle),
                    "from": int(bit1_prev),
                    "to": int(bit1_now),
                    "flags": int(ctl_mem.flags),
                    "lcd0": lcd_lines[0].rstrip(),
                    "lcd1": lcd_lines[1].rstrip(),
                    "ctl_input": int(ctl_mem.input_sel),
                    "ctl_volume": int(ctl_mem.volume),
                    "main0_status_5e": int(main_mem0.status_5e),
                    "main0_mb": {
                        "rd": int(main_mem0.mb_rd),
                        "wr": int(main_mem0.mb_wr),
                        "txwr": int(main_mem0.mb_tx_wr),
                    },
                    "window_frames": win,
                }
                if main1 is not None:
                    ev["main1_status_5e"] = int(main_mem1.status_5e)
                    ev["main1_mb"] = {
                        "rd": int(main_mem1.mb_rd),
                        "wr": int(main_mem1.mb_wr),
                        "txwr": int(main_mem1.mb_tx_wr),
                    }
                bit1_events.append(ev)
                print(
                    f"  bit1 {bit1_prev}->{bit1_now}  cycle=0x{ctl_cycle:08X}  "
                    f"flags=0x{ctl_mem.flags:02X}  "
                    f"lcd='{lcd_lines[0].rstrip()}'/{lcd_lines[1].rstrip()}'  "
                    f"m0_5e=0x{main_mem0.status_5e:02X}  "
                    f"oerr c2m0={link_ctl_m0.overrun_total} m02c={link_m0_ctl.overrun_total}"
                )
                bit1_prev = bit1_now

            if (ctl_cycle - last_sample_cycle) >= args.sample_every_cycles:
                snap: Dict[str, object] = {
                    "cycle": int(ctl_cycle),
                    "lcd0": lcd_lines[0].rstrip(),
                    "lcd1": lcd_lines[1].rstrip(),
                    "flags": int(ctl_mem.flags),
                    "bit1": int((ctl_mem.flags >> 1) & 1),
                    "main0_status_5e": int(main_mem0.status_5e),
                    "m0_mb": {
                        "rd": int(main_mem0.mb_rd),
                        "wr": int(main_mem0.mb_wr),
                        "txwr": int(main_mem0.mb_tx_wr),
                    },
                }
                if main1 is not None:
                    snap["main1_status_5e"] = int(main_mem1.status_5e)
                    snap["m1_mb"] = {
                        "rd": int(main_mem1.mb_rd),
                        "wr": int(main_mem1.mb_wr),
                        "txwr": int(main_mem1.mb_tx_wr),
                    }
                snapshots.append(snap)
                _progress("measure", ctl_cycle)
                last_sample_cycle = ctl_cycle

        sys.stderr.write("\n")

        link_stats: Dict[str, object] = {}
        for lk in all_links:
            link_stats[lk.name] = {
                "overrun_total": lk.overrun_total,
                "delivered_total": lk.delivered_total,
                "queue_len": len(lk),
                "byte_cycles": lk.byte_cycles,
                "fifo_depth": lk.fifo_depth,
            }

        cmd03_by_src_data = Counter(
            (str(x["src"]), int(x["data"])) for x in all_tx if int(x["cmd"]) == 0x03
        )
        cmd04_by_src = Counter(str(x["src"]) for x in all_tx if int(x["cmd"]) == 0x04)

        payload = {
            "config": {
                "control_hex": str(args.control_hex),
                "main_hexes": [str(p) for p in main_hexes],
                "single_main": single_main,
                "gpasm": args.gpasm,
                "duration_s": float(args.duration_s),
                "control_ips": float(args.control_ips),
                "warmup_cycles": int(args.warmup_cycles),
                "target_cycles": int(target_cycles),
                "chunk_cycles": int(args.chunk_cycles),
                "main_chunk_cycles": int(args.main_chunk_cycles),
                "main0_standby": args.main0_standby,
                "main_ra0": int(args.main_ra0),
                "main0_rc2": args.main0_rc2,
                "main_timer3": args.main_timer3,
                "rx_fifo_limit": fifo,
                "byte_cycles_ctl": ctl_byte_cyc,
                "byte_cycles_main": main_byte_cyc,
                "fast_boot": bool(args.fast_boot),
            },
            "stats": {
                "total_frames": len(all_tx),
                "bit1_events": len(bit1_events),
                "cmd03_by_src_data": {
                    f"{k[0]}_d{k[1]}": v for k, v in sorted(cmd03_by_src_data.items())
                },
                "cmd04_by_src": dict(sorted(cmd04_by_src.items())),
                "link_stats": link_stats,
            },
            "bit1_events": bit1_events,
            "snapshots": snapshots,
            "tx_frames": all_tx,
        }

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        print(f"\nwrote {args.output}")
        print(json.dumps(payload["stats"], indent=2))
        for i, ev in enumerate(bit1_events, 1):
            print(
                f"event#{i} cycle=0x{ev['ctl_cycle']:08X} "
                f"{ev['from']}->{ev['to']} flags=0x{ev['flags']:02X} "
                f"lcd='{ev['lcd0']}'/'{ev['lcd1']}'"
            )
        return 0
    finally:
        if main1 is not None:
            main1.close()
        main0.close()
        control.close()


if __name__ == "__main__":
    raise SystemExit(main())
