#!/usr/bin/env python3
"""
Run control firmware in gpsim and decode HD44780 traffic from PORT/LAT writes.

This is a practical middle ground:
- Uses real PIC instruction execution in gpsim.
- Decodes LCD nibbles from logged `iorwf portb` writes and RS changes on RA5.

Notes:
- The stock reset vector jumps to bootloader (0x7800). In gpsim, USB bootloader
  paths can stall. By default this tool patches reset to `goto 0x0040` in a
  temporary simulation-only HEX so the app UI code runs.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Dict, List, Tuple

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dlcp_fw.paths import SIM_ARTIFACTS_DIR, STOCK_CONTROL_HEX_V14


def parse_intel_hex(path: pathlib.Path) -> Dict[int, int]:
    mem: Dict[int, int] = {}
    upper = 0
    for lineno, line in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        if not line.startswith(":"):
            raise RuntimeError(f"{path}:{lineno}: invalid HEX")
        ll = int(line[1:3], 16)
        aaaa = int(line[3:7], 16)
        rtype = int(line[7:9], 16)
        data = bytes.fromhex(line[9 : 9 + ll * 2])
        if rtype == 0x00:
            base = (upper << 16) | aaaa
            for i, b in enumerate(data):
                mem[base + i] = b
        elif rtype == 0x01:
            break
        elif rtype == 0x04:
            if ll != 2:
                raise RuntimeError(f"{path}:{lineno}: bad type04 len={ll}")
            upper = (data[0] << 8) | data[1]
    return mem


def _rec(addr16: int, rtype: int, payload: bytes) -> str:
    ll = len(payload)
    total = ll + ((addr16 >> 8) & 0xFF) + (addr16 & 0xFF) + rtype + sum(payload)
    cc = (~total + 1) & 0xFF
    return f":{ll:02X}{addr16:04X}{rtype:02X}{payload.hex().upper()}{cc:02X}"


def write_intel_hex(path: pathlib.Path, mem: Dict[int, int], chunk: int = 16) -> None:
    addrs = sorted(mem.keys())
    out: List[str] = []
    cur_upper: int | None = None
    i = 0
    while i < len(addrs):
        a = addrs[i]
        upper = (a >> 16) & 0xFFFF
        if upper != cur_upper:
            cur_upper = upper
            out.append(_rec(0x0000, 0x04, bytes([(upper >> 8) & 0xFF, upper & 0xFF])))
        a16 = a & 0xFFFF
        data = bytearray([mem[a] & 0xFF])
        i += 1
        while i < len(addrs):
            b = addrs[i]
            if ((b >> 16) & 0xFFFF) != upper:
                break
            if (b & 0xFFFF) != ((a16 + len(data)) & 0xFFFF):
                break
            if len(data) >= chunk:
                break
            data.append(mem[b] & 0xFF)
            i += 1
        out.append(_rec(a16, 0x00, bytes(data)))
    out.append(":00000001FF")
    path.write_text("\n".join(out) + "\n", encoding="ascii")


def make_appstart_hex(src_hex: pathlib.Path, dst_hex: pathlib.Path) -> None:
    mem = parse_intel_hex(src_hex)
    # PIC18 goto 0x0040 bytes from gpasm:
    # :04000000 20 EF 00 F0
    mem[0x0000] = 0x20
    mem[0x0001] = 0xEF
    mem[0x0002] = 0x00
    mem[0x0003] = 0xF0
    write_intel_hex(dst_hex, mem)


@dataclass
class LcdByte:
    cycle: int
    rs: int
    value: int
    n1: int
    n2: int


def decode_lcd_bytes(log_path: pathlib.Path) -> List[LcdByte]:
    ins_re = re.compile(r"^0x([0-9A-Fa-f]+)\s+\S+\s+0x([0-9A-Fa-f]+)\s+0x([0-9A-Fa-f]+)\s+(.*)$")
    w_re = re.compile(r"Read:\s+0x([0-9A-Fa-f]+)\s+from W\(0x0FE8\)")

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()

    rs = 0
    pending: Tuple[int, int] | None = None
    nibbles: List[Tuple[int, int, int]] = []

    for line in lines:
        m = ins_re.match(line)
        if m:
            cycle = int(m.group(1), 16)
            op = m.group(4).lower()
            if "bcf\tlata,5" in op:
                rs = 0
            elif "bsf\tlata,5" in op:
                rs = 1

            if "iorwf\tportb" in op:
                pending = (cycle, rs)
            else:
                pending = None
            continue

        if pending is None:
            continue
        mw = w_re.search(line)
        if not mw:
            continue
        w = int(mw.group(1), 16)
        nibbles.append((pending[0], pending[1], w & 0x0F))

    out: List[LcdByte] = []
    for i in range(0, len(nibbles) - 1, 2):
        c1, rs1, n1 = nibbles[i]
        c2, rs2, n2 = nibbles[i + 1]
        b = ((n1 << 4) | n2) & 0xFF
        out.append(LcdByte(cycle=c2, rs=rs2, value=b, n1=n1, n2=n2))
    return out


@dataclass
class LcdState:
    ddram: List[str]
    cursor: int = 0

    @staticmethod
    def new() -> "LcdState":
        return LcdState(ddram=[" "] * 0x80, cursor=0)

    def line1(self) -> str:
        return "".join(self.ddram[0x00 : 0x10])

    def line2(self) -> str:
        return "".join(self.ddram[0x40 : 0x50])

    def apply(self, b: LcdByte) -> str:
        if b.rs == 0:
            v = b.value
            if v == 0x01:
                self.ddram = [" "] * 0x80
                self.cursor = 0
                return "CMD CLR"
            if v == 0x02:
                self.cursor = 0
                return "CMD HOME"
            if v & 0x80:
                self.cursor = v & 0x7F
                return f"CMD SET_DDRAM 0x{self.cursor:02X}"
            return f"CMD 0x{v:02X}"

        ch = chr(b.value) if 32 <= b.value < 127 else "?"
        if 0 <= self.cursor < len(self.ddram):
            self.ddram[self.cursor] = ch
        self.cursor = (self.cursor + 1) & 0x7F
        return f"DATA '{ch}' (0x{b.value:02X})"


def run_gpsim(hex_path: pathlib.Path, cycles: int, out_log: pathlib.Path, out_cli: pathlib.Path) -> str:
    stc = out_cli.with_suffix(".stc")
    stc.write_text(
        "\n".join(
            [
                "processor p18f2550",
                f"load {hex_path}",
                f"log on {out_log}",
                "log w porta",
                "log w portb",
                "log w trisa",
                "log w trisb",
                "log w lata",
                "log w latb",
                f"break c {cycles}",
                "run",
                "log off",
                "quit",
                "",
            ]
        ),
        encoding="ascii",
    )
    cp = subprocess.run(
        ["gpsim", "-i", "-c", str(stc)],
        text=True,
        capture_output=True,
        check=True,
    )
    out_cli.write_text(cp.stdout + cp.stderr, encoding="utf-8")
    return cp.stdout + cp.stderr


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--hex",
        type=pathlib.Path,
        default=STOCK_CONTROL_HEX_V14,
        help="input control HEX",
    )
    ap.add_argument("--cycles", type=int, default=50_000_000, help="gpsim cycles to run")
    ap.add_argument(
        "--no-appstart-patch",
        action="store_true",
        help="do not patch reset vector to app start (0x0040)",
    )
    ap.add_argument("--keep-temp", action="store_true", help="keep temp files")
    ap.add_argument("--show-events", type=int, default=80, help="how many decoded events to print")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory(prefix="gpsim_lcd_") as td:
        td_path = pathlib.Path(td)
        sim_hex = td_path / "sim.hex"
        log_path = td_path / "gpsim.log"
        cli_path = td_path / "gpsim_cli.txt"

        src_hex = args.hex.resolve()
        if args.no_appstart_patch:
            sim_hex.write_bytes(src_hex.read_bytes())
        else:
            make_appstart_hex(src_hex, sim_hex)

        cli_text = run_gpsim(sim_hex, args.cycles, log_path, cli_path)
        if "cycle break:" not in cli_text:
            raise RuntimeError("gpsim run ended without cycle break; inspect CLI log")

        lcd_bytes = decode_lcd_bytes(log_path)
        st = LcdState.new()
        events: List[Tuple[int, str, str, str]] = []
        for b in lcd_bytes:
            ev = st.apply(b)
            events.append((b.cycle, ev, st.line1(), st.line2()))

        print(f"hex: {src_hex}")
        print(f"cycles: {args.cycles}")
        print(f"decoded lcd bytes: {len(lcd_bytes)}")
        print(f"data bytes (RS=1): {sum(1 for b in lcd_bytes if b.rs == 1)}")
        print(f"cmd bytes  (RS=0): {sum(1 for b in lcd_bytes if b.rs == 0)}")
        print()
        print("Final LCD:")
        print(f"|{st.line1()}|")
        print(f"|{st.line2()}|")
        print()
        print("Last decoded events:")
        for cyc, ev, l1, l2 in events[-args.show_events :]:
            print(f"0x{cyc:X} {ev}")
            print(f"  |{l1}|")
            print(f"  |{l2}|")

        if args.keep_temp:
            keep = SIM_ARTIFACTS_DIR / "tmp_gpsim_lcd_capture"
            keep.mkdir(parents=True, exist_ok=True)
            (keep / "sim.hex").write_bytes(sim_hex.read_bytes())
            (keep / "gpsim.log").write_bytes(log_path.read_bytes())
            (keep / "gpsim_cli.txt").write_text(cli_text, encoding="utf-8")
            print()
            print(f"saved artifacts: {keep}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
