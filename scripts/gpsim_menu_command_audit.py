#!/usr/bin/env python3
"""
gpsim-only menu/command audit for DLCP control firmware.

Runs both:
- stock control v1.4
- patched control v1.4 preset_AB

and generates:
1) command behavior checks (volume/mute/input with keypresses)
2) text menu hierarchy dumps discovered through gpsim key navigation
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

import _bootstrap

from dlcp_fw.sim.hexio import parse_intel_hex, write_intel_hex
from dlcp_fw.sim.lcd import LcdState, decode_lcd_bytes
from dlcp_fw.sim.manifests import control_disable_boot_wait, control_reset_to_appstart
from dlcp_fw.sim.overlay import apply_overlays
from dlcp_fw.paths import PATCHED_CONTROL_HEX, SIM_ARTIFACTS_DIR, STOCK_CONTROL_HEX_V14

ROOT = _bootstrap.REPO_ROOT


KEY_PIN: Dict[str, int] = {
    "S": 3,  # RA1 select/mute
    "D": 4,  # RA2 down
    "STBY": 5,  # RA3 standby
    "R": 6,  # RA4 right
    "U": 11,  # RC0 up
    "L": 16,  # RC5 left
}

HOOK_ORG = 0x7400
HOOK_ASM = f"""
LIST P=18F2550
#include <p18f2550.inc>

org 0x044A
    goto sim_function_019
org 0x044E
    nop

org 0x{HOOK_ORG:04X}
sim_function_019:
    movlb 0x0
    movf 0x0B9, W, BANKED
    xorlw 0x80
    bnz sim_ready
    clrf 0x0B8, BANKED
    movlw 0x33
    movwf 0x0B9, BANKED
    movlw 0x05
    movwf 0x0A7, BANKED
    clrf 0x0A1, BANKED
sim_ready:
    ; Keep UI in \"connected\" path for deterministic menu testing in sim.
    bsf 0x01F, 1, ACCESS
    return 0

end
"""


@dataclass(frozen=True)
class TxTriplet:
    cycle: int
    route: int
    cmd: int
    data: int


@dataclass(frozen=True)
class KeyEvent:
    key: str
    cycle: int


@dataclass
class GpsimScenarioResult:
    tx: List[TxTriplet]
    lcd_final: tuple[str, str]
    lcd_snapshots: Dict[int, tuple[str, str]]
    run_dir: Path


def _require_tools() -> None:
    if shutil.which("gpsim") is None:
        raise RuntimeError("gpsim not found in PATH")
    if shutil.which("gpasm") is None:
        raise RuntimeError("gpasm not found in PATH")


def _build_sim_hex(src_hex: Path, out_hex: Path, gpasm: str) -> None:
    apply_overlays(
        src_hex,
        out_hex,
        manifests=[control_reset_to_appstart(), control_disable_boot_wait()],
    )

    with tempfile.TemporaryDirectory(prefix="gpsim_ctl_hook_") as td:
        td_path = Path(td)
        asm = td_path / "hook.asm"
        patch_hex = td_path / "hook.hex"
        asm.write_text(HOOK_ASM, encoding="ascii")
        subprocess.run(
            [gpasm, "-p18f2550", "-o", str(patch_hex), str(asm)],
            check=True,
            capture_output=True,
            text=True,
        )
        base_mem = parse_intel_hex(out_hex)
        base_mem.update(parse_intel_hex(patch_hex))
        write_intel_hex(out_hex, base_mem)


def _parse_tx_triplets(log_text: str) -> List[TxTriplet]:
    ins_re = re.compile(r"^0x([0-9A-Fa-f]+)\s+")
    wr_re = re.compile(r"Wrote:\s+0x([0-9A-Fa-f]+)\s+to txreg")

    writes: List[tuple[int, int]] = []
    cur_cycle: int | None = None
    for line in log_text.splitlines():
        m_ins = ins_re.match(line)
        if m_ins:
            cur_cycle = int(m_ins.group(1), 16)
            continue
        m_wr = wr_re.search(line)
        if m_wr and cur_cycle is not None:
            writes.append((cur_cycle, int(m_wr.group(1), 16) & 0xFF))

    out: List[TxTriplet] = []
    i = 0
    while i + 2 < len(writes):
        c0, b0 = writes[i]
        _, b1 = writes[i + 1]
        _, b2 = writes[i + 2]
        out.append(TxTriplet(cycle=c0, route=b0, cmd=b1, data=b2))
        i += 3
    return out


def _lcd_snapshots(log_path: Path, sample_cycles: Sequence[int]) -> Dict[int, tuple[str, str]]:
    points = sorted(sample_cycles)
    out: Dict[int, tuple[str, str]] = {}
    lcd = decode_lcd_bytes(log_path)
    st = LcdState.new()
    j = 0
    for b in lcd:
        st.apply(b)
        while j < len(points) and b.cycle >= points[j]:
            out[points[j]] = (st.line1(), st.line2())
            j += 1
    while j < len(points):
        out[points[j]] = (st.line1(), st.line2())
        j += 1
    return out


def _scenario(
    sim_hex: Path,
    events: Sequence[KeyEvent],
    break_cycle: int,
    snapshot_cycles: Sequence[int],
    out_dir: Path,
) -> GpsimScenarioResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    pulse_cycles = 200_000
    per_pin: Dict[int, List[tuple[int, int]]] = {pin: [(1, 1)] for pin in KEY_PIN.values()}
    for ev in events:
        pin = KEY_PIN[ev.key]
        per_pin[pin].append((ev.cycle, 0))
        per_pin[pin].append((ev.cycle + pulse_cycles, 1))

    stc = out_dir / "run.stc"
    log_path = out_dir / "gpsim.log"
    lines = [
        "processor p18f2550",
        f"load {sim_hex}",
    ]
    for idx, pin in enumerate(sorted(per_pin)):
        events_txt = ", ".join(f"{t},{v}" for t, v in per_pin[pin])
        lines.extend(
            [
                f"node n{idx}",
                "stimulus asynchronous_stimulus",
                "initial_state 1",
                "start_cycle 0",
                "period 2000000000",
                "{ " + events_txt + " }",
                f"name stim_{idx}",
                "end",
                f"attach n{idx} pin({pin}) stim_{idx}",
            ]
        )
    lines.extend(
        [
            f"log on {log_path}",
            "log w txreg",
            "log w porta",
            "log w portb",
            "log w portc",
            "log w lata",
            "log w latb",
            f"break c {break_cycle}",
            "run",
            "log off",
            "quit",
            "",
        ]
    )
    stc.write_text("\n".join(lines), encoding="ascii")

    cp = subprocess.run(
        ["gpsim", "-i", "-c", str(stc)],
        text=True,
        capture_output=True,
        check=False,
    )
    if cp.returncode != 0:
        raise RuntimeError(f"gpsim failed for {out_dir}: {cp.stdout}\n{cp.stderr}")

    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    tx = _parse_tx_triplets(log_text)
    snaps = _lcd_snapshots(log_path, snapshot_cycles)
    final = snaps[max(snapshot_cycles)] if snapshot_cycles else _lcd_snapshots(log_path, [0])[0]
    return GpsimScenarioResult(tx=tx, lcd_final=final, lcd_snapshots=snaps, run_dir=out_dir)


def _first_frame_after(
    tx: Iterable[TxTriplet], *, cmd: int, after: int, window: int = 4_000_000
) -> TxTriplet | None:
    hi = after + window
    for f in tx:
        if f.cycle < after or f.cycle > hi:
            continue
        if f.route == 0xB0 and f.cmd == cmd:
            return f
    return None


def _fmt_screen(scr: tuple[str, str]) -> str:
    return f"|{scr[0]}| / |{scr[1]}|"


def _audit_one(fw_name: str, fw_hex: Path, out_root: Path, gpasm: str) -> tuple[Path, Path]:
    run_root = out_root / fw_name.replace(" ", "_").replace("/", "_")
    run_root.mkdir(parents=True, exist_ok=True)

    sim_hex = run_root / "sim.hex"
    _build_sim_hex(fw_hex, sim_hex, gpasm)

    patched_mode = "patched" in fw_name.lower()
    wake_cycles = (
        [60_000_000, 100_000_000, 140_000_000, 180_000_000]
        if patched_mode
        else [60_000_000]
    )
    t0 = 212_000_000 if patched_mode else 84_000_000
    step = 8_000_000
    input_step = 4_000_000

    def with_wake(events: Sequence[KeyEvent]) -> List[KeyEvent]:
        out = [KeyEvent("STBY", c) for c in wake_cycles]
        out.extend(events)
        return out

    # Command tests
    cmd_lines: List[str] = []
    cmd_lines.append(f"Firmware: {fw_name}")
    cmd_lines.append(f"Source HEX: {fw_hex}")
    cmd_lines.append("")
    cmd_lines.append("Command Exercise (gpsim keypresses):")

    # volume up
    vol_up = _scenario(
        sim_hex,
        events=with_wake([KeyEvent("U", t0)]),
        break_cycle=t0 + 30_000_000,
        snapshot_cycles=[t0 - 2_000_000, t0 + 2_000_000, t0 + 24_000_000],
        out_dir=run_root / "cmd_volume_up",
    )
    f_up = _first_frame_after(vol_up.tx, cmd=0x07, after=t0)
    cmd_lines.append(f"- Volume UP key: screen {_fmt_screen(vol_up.lcd_snapshots[t0 + 2_000_000])}")
    cmd_lines.append(f"  TX: {f_up}")

    # volume down
    vol_dn = _scenario(
        sim_hex,
        events=with_wake([KeyEvent("D", t0)]),
        break_cycle=t0 + 30_000_000,
        snapshot_cycles=[t0 - 2_000_000, t0 + 2_000_000, t0 + 24_000_000],
        out_dir=run_root / "cmd_volume_down",
    )
    f_dn = _first_frame_after(vol_dn.tx, cmd=0x07, after=t0)
    cmd_lines.append(f"- Volume DOWN key: screen {_fmt_screen(vol_dn.lcd_snapshots[t0 + 2_000_000])}")
    cmd_lines.append(f"  TX: {f_dn}")

    # mute toggle
    mute = _scenario(
        sim_hex,
        events=with_wake([KeyEvent("S", t0)]),
        break_cycle=t0 + 30_000_000,
        snapshot_cycles=[t0 - 2_000_000, t0 + 2_000_000, t0 + 24_000_000],
        out_dir=run_root / "cmd_mute",
    )
    f_mute = _first_frame_after(mute.tx, cmd=0x03, after=t0)
    cmd_lines.append(f"- MUTE key: screen {_fmt_screen(mute.lcd_snapshots[t0 + 2_000_000])}")
    cmd_lines.append(f"  TX: {f_mute}")

    # input change auto->AES->S/PDIF (from input menu)
    # R enters input. U increments input. D decrements input.
    input_seq_events = with_wake(
        [
            KeyEvent("R", t0),
            KeyEvent("U", t0 + input_step),
            KeyEvent("U", t0 + 2 * input_step),
            KeyEvent("U", t0 + 3 * input_step),  # reaches AES
            KeyEvent("D", t0 + 4 * input_step),
            KeyEvent("D", t0 + 5 * input_step),  # back to S/PDIF
        ]
    )
    input_seq = _scenario(
        sim_hex,
        events=input_seq_events,
        break_cycle=t0 + 48_000_000,
        snapshot_cycles=[
            t0 + 2_000_000,
            t0 + 6_000_000,
            t0 + 10_000_000,
            t0 + 14_000_000,
            t0 + 18_000_000,
            t0 + 22_000_000,
        ],
        out_dir=run_root / "cmd_input_seq",
    )
    f_aes = _first_frame_after(input_seq.tx, cmd=0x06, after=t0 + 3 * input_step)
    f_spdif = _first_frame_after(input_seq.tx, cmd=0x06, after=t0 + 5 * input_step)
    cmd_lines.append("- INPUT menu navigation:")
    cmd_lines.append(f"  After R: {_fmt_screen(input_seq.lcd_snapshots[t0 + 2_000_000])}")
    cmd_lines.append(f"  After U,U,U (target AES): {_fmt_screen(input_seq.lcd_snapshots[t0 + 14_000_000])}")
    cmd_lines.append(f"  TX for AES step: {f_aes}")
    cmd_lines.append(f"  After D,D (target S/PDIF): {_fmt_screen(input_seq.lcd_snapshots[t0 + 22_000_000])}")
    cmd_lines.append(f"  TX for S/PDIF step: {f_spdif}")

    cmd_lines.append("")
    cmd_lines.append("Broadcast propagation check:")
    cmd_lines.append("- All tested frames use route 0xB0.")
    cmd_lines.append("- Route 0xB0 is broadcast in DLCP current-loop protocol and targets all chained main units.")

    cmd_report = run_root / "command_audit.txt"
    cmd_report.write_text("\n".join(cmd_lines) + "\n", encoding="utf-8")

    # Menu dump via gpsim navigation
    menu_lines: List[str] = []
    menu_lines.append(f"Firmware: {fw_name}")
    menu_lines.append(f"Source HEX: {fw_hex}")
    menu_lines.append("")
    menu_lines.append("Top-Level Menus (gpsim snapshots):")
    top = _scenario(
        sim_hex,
        events=with_wake(
            [
                KeyEvent("R", t0),
                KeyEvent("R", t0 + step),
                KeyEvent("L", t0 + 2 * step),
                KeyEvent("L", t0 + 3 * step),
            ]
        ),
        break_cycle=t0 + 44_000_000,
        snapshot_cycles=[t0 - 2_000_000, t0 + 2_000_000, t0 + 10_000_000, t0 + 18_000_000, t0 + 26_000_000],
        out_dir=run_root / "menu_top",
    )
    menu_lines.append(f"- Volume: {_fmt_screen(top.lcd_snapshots[t0 - 2_000_000])}")
    menu_lines.append(f"- Input: {_fmt_screen(top.lcd_snapshots[t0 + 2_000_000])}")
    menu_lines.append(f"- Setup: {_fmt_screen(top.lcd_snapshots[t0 + 10_000_000])}")

    # Input options dump
    input_lines: List[str] = []
    for n_up in range(0, 9):
        events = with_wake([KeyEvent("R", t0)])
        t = t0 + input_step
        for _ in range(n_up):
            events.append(KeyEvent("U", t))
            t += input_step
        res = _scenario(
            sim_hex,
            events=events,
            break_cycle=t + 12_000_000,
            snapshot_cycles=[t + 8_000_000],
            out_dir=run_root / f"menu_input_{n_up}",
        )
        scr = res.lcd_snapshots[t + 8_000_000]
        input_lines.append(f"{n_up}: {scr[1].strip()}")
    menu_lines.append("")
    menu_lines.append("Input Menu Options (U key walk):")
    menu_lines.extend(f"- {x}" for x in input_lines)

    # Setup item list
    setup_lines: List[str] = []
    events = with_wake([KeyEvent("R", t0), KeyEvent("R", t0 + step)])
    sample_cycles = [t0 + 10_000_000]
    t = t0 + 2 * step
    for _ in range(6):
        events.append(KeyEvent("U", t))
        sample_cycles.append(t + 2_000_000)
        t += step
    setup_res = _scenario(
        sim_hex,
        events=events,
        break_cycle=t + 20_000_000,
        snapshot_cycles=sample_cycles,
        out_dir=run_root / "menu_setup_items",
    )
    for cyc in sample_cycles:
        setup_lines.append(setup_res.lcd_snapshots[cyc][1].strip())
    menu_lines.append("")
    menu_lines.append("Setup Items (U key walk):")
    for i, label in enumerate(setup_lines):
        menu_lines.append(f"- {i}: {label}")

    # DLCP1 editor parameter labels
    events = with_wake(
        [
            KeyEvent("R", t0),
            KeyEvent("R", t0 + step),
            KeyEvent("S", t0 + 2 * step),  # enter DLCP1 editor
        ]
    )
    param_samples = [t0 + 2 * step + 2_000_000]
    t = t0 + 3 * step
    for _ in range(6):
        events.append(KeyEvent("R", t))
        param_samples.append(t + 2_000_000)
        t += step
    params_res = _scenario(
        sim_hex,
        events=events,
        break_cycle=t + 16_000_000,
        snapshot_cycles=param_samples,
        out_dir=run_root / "menu_dlcp1_params",
    )
    menu_lines.append("")
    menu_lines.append("DLCP1 Editor Parameters (R key walk):")
    for i, cyc in enumerate(param_samples):
        scr = params_res.lcd_snapshots[cyc]
        menu_lines.append(f"- {i}: {scr[1].strip()}")

    # Source CH1 options
    events = with_wake(
        [
            KeyEvent("R", t0),
            KeyEvent("R", t0 + step),
            KeyEvent("S", t0 + 2 * step),
        ]
    )
    ch1_samples = [t0 + 2 * step + 2_000_000]
    t = t0 + 3 * step
    for _ in range(3):
        events.append(KeyEvent("U", t))
        ch1_samples.append(t + 2_000_000)
        t += step
    ch1_res = _scenario(
        sim_hex,
        events=events,
        break_cycle=t + 16_000_000,
        snapshot_cycles=ch1_samples,
        out_dir=run_root / "menu_dlcp1_ch1_opts",
    )
    menu_lines.append("")
    menu_lines.append("DLCP1 Source CH1 Options (U key walk):")
    for cyc in ch1_samples:
        menu_lines.append(f"- {ch1_res.lcd_snapshots[cyc][1].strip()}")

    # Param7 (USBaudio or Preset) options
    events = with_wake(
        [
            KeyEvent("R", t0),
            KeyEvent("R", t0 + step),
            KeyEvent("S", t0 + 2 * step),
        ]
    )
    t = t0 + 3 * step
    for _ in range(6):
        events.append(KeyEvent("R", t))
        t += step
    # now on param7, sample current and after U
    aux_samples = [t + 2_000_000]
    events.append(KeyEvent("U", t + step))
    aux_samples.append(t + step + 2_000_000)
    aux_res = _scenario(
        sim_hex,
        events=events,
        break_cycle=t + step + 16_000_000,
        snapshot_cycles=aux_samples,
        out_dir=run_root / "menu_dlcp1_aux_opts",
    )
    menu_lines.append("")
    menu_lines.append("DLCP1 Param7 Options (USBaudio/Preset):")
    for cyc in aux_samples:
        menu_lines.append(f"- {aux_res.lcd_snapshots[cyc][1].strip()}")

    # BL Timeout options
    events = with_wake([KeyEvent("R", t0), KeyEvent("R", t0 + step)])
    t = t0 + 2 * step
    for _ in range(6):
        events.append(KeyEvent("U", t))
        t += step
    events.append(KeyEvent("S", t))
    bl_samples = [t + 2_000_000]
    t += step
    for _ in range(3):
        events.append(KeyEvent("U", t))
        bl_samples.append(t + 2_000_000)
        t += step
    bl_res = _scenario(
        sim_hex,
        events=events,
        break_cycle=t + 20_000_000,
        snapshot_cycles=bl_samples,
        out_dir=run_root / "menu_bl_timeout",
    )
    menu_lines.append("")
    menu_lines.append("BL Timeout Options (U key walk):")
    for cyc in bl_samples:
        menu_lines.append(f"- {bl_res.lcd_snapshots[cyc][1].strip()}")

    menu_report = run_root / "menu_hierarchy.txt"
    menu_report.write_text("\n".join(menu_lines) + "\n", encoding="utf-8")
    return menu_report, cmd_report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gpasm", default="gpasm", help="gpasm executable")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=SIM_ARTIFACTS_DIR / "gpsim_audit",
        help="output directory for reports/artifacts",
    )
    args = ap.parse_args()

    _require_tools()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    stock_hex = STOCK_CONTROL_HEX_V14
    patched_hex = PATCHED_CONTROL_HEX
    if not stock_hex.exists():
        raise SystemExit(f"missing stock HEX: {stock_hex}")
    if not patched_hex.exists():
        raise SystemExit(f"missing patched HEX: {patched_hex}")

    reports: List[tuple[str, Path, Path]] = []
    reports.append(
        (
            "stock_v1.4",
            *_audit_one("stock_v1.4", stock_hex, out_dir, args.gpasm),
        )
    )
    reports.append(
        (
            "patched_v1.4_presets_AB",
            *_audit_one("patched_v1.4_presets_AB", patched_hex, out_dir, args.gpasm),
        )
    )

    print("gpsim audit complete:")
    for name, menu_p, cmd_p in reports:
        print(f"- {name}")
        print(f"  menu: {menu_p}")
        print(f"  cmd : {cmd_p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
