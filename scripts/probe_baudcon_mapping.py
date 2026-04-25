#!/usr/bin/env python3
"""probe_baudcon_mapping.py — settle the §11b BAUDCON open question.

The original `docs/SIM_REWRITE_RUST_SPEC.md` §11b assumes the PIC18F2455
datasheet places BAUDCON at 0xF98 (and treats gpsim's 0xFB8 mapping as
"wrong, inherited from P18F2x21").  This probe runs the V3.2 MAIN hex
under gpsim and observes empirically:

  1. Where the assembled firmware actually writes `movwf BAUDCON, ACCESS`.
  2. Which address gpsim sees that write at.
  3. The post-write residue at both 0xFB8 and 0xF98.

A clean run prints a verdict naming exactly which of the §11b
explanations holds and exits 0.  The probe also asserts that the V3.2
hex contains the FB8-form opcode (`6EB8`) and *not* the F98-form
opcode (`6E98`) — this is the static half of the proof and runs even
if gpsim is unavailable.

Verify gate: ``.venv_ep0/bin/python scripts/probe_baudcon_mapping.py``.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dlcp_fw.paths import V32_MAIN_HEX  # noqa: E402
from dlcp_fw.sim.gpsim import resolve_gpsim_binary  # noqa: E402
from dlcp_fw.sim.main_gpsim import write_main_an0_bootstrap_stc  # noqa: E402
from dlcp_fw.sim.v30_symbols import find_code_signature  # noqa: E402

# Opcode encoding for the firmware's BAUDCON write.
# `movlw 0x48` -> 0E48 -> bytes 48 0E (little-endian word).
# `movwf 0xFB8, ACCESS=0` -> 6EB8 -> bytes B8 6E.
SIG_FB8 = bytes.fromhex("480eb86e")
# Hypothetical alternative if the firmware were targeting 0xF98:
# `movwf 0xF98, ACCESS=0` -> 6E98 -> bytes 98 6E.
SIG_F98 = bytes.fromhex("480e986e")

PROCESSOR = "p18f2455"
FOSC_HZ = 16_000_000
GPSIM_RUN_CYCLES = 250_000  # generous budget; uart_config runs early.


def static_check(main_hex: Path) -> tuple[int | None, int | None]:
    """Return (fb8_addr, f98_addr) for the two signature forms in the hex."""
    fb8 = find_code_signature(main_hex, SIG_FB8)
    f98 = find_code_signature(main_hex, SIG_F98)
    return fb8, f98


def _build_probe_stc(
    out_dir: Path,
    sim_hex: Path,
    log_path: Path,
    bootstrap_stc: Path,
    break_pc: int,
    fallback_cycles: int,
) -> Path:
    stc = out_dir / "probe_baudcon.stc"
    body = "\n".join(
        [
            f"processor {PROCESSOR}",
            f"load {sim_hex}",
            f"frequency {FOSC_HZ}",
            f"load {bootstrap_stc}",
            f"log on {log_path}",
            "log w baudcon",
            f"break e 0x{break_pc:04X}",
            f"break c {fallback_cycles}",
            "run",
            "log off",
            # Dump residues at both candidate addresses so the parent
            # can compare without relying on log-line shape alone.
            "reg(0xfb8)",
            "reg(0xf98)",
            "quit",
            "",
        ]
    )
    stc.write_text(body, encoding="ascii")
    return stc


def _parse_baudcon_writes(log_text: str) -> list[tuple[int, int, int]]:
    """Return deduplicated [(cycle, value, addr)] entries.

    gpsim emits each register-write event over two log lines:
      0x000000000000XXXX p18f2455 0xPCPC 0xOPOP movwf\tbaudcon
        Wrote: 0x0048 to baudcon(0x0FB8) was 0x0000

    The address inside `baudcon(...)` is captured so the verdict can
    insist that gpsim actually mapped BAUDCON at 0xFB8 — without that
    check, a future gpsim refactor that renamed a different register
    "baudcon" or aliased BAUDCON to 0xF98 would silently slip past.

    A breakpoint that fires on the same instruction can cause gpsim to
    duplicate the pair; we collapse identical (cycle, value, addr)
    tuples.
    """
    cycle_re = re.compile(
        r"^0x([0-9A-Fa-f]+)\s+\S+\s+0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+movwf"
    )
    write_re = re.compile(
        r"Wrote:?\s+0x([0-9A-Fa-f]+)\s+to\s+baudcon\(0x([0-9A-Fa-f]+)\)",
        re.IGNORECASE,
    )
    out: list[tuple[int, int, int]] = []
    cycle: int | None = None
    for line in log_text.splitlines():
        cm = cycle_re.match(line)
        if cm:
            cycle = int(cm.group(1), 16)
            continue
        wm = write_re.search(line)
        if wm:
            out.append((
                cycle if cycle is not None else 0,
                int(wm.group(1), 16) & 0xFF,
                int(wm.group(2), 16) & 0xFFFF,
            ))
            cycle = None
    deduped: list[tuple[int, int, int]] = []
    for entry in out:
        if not deduped or deduped[-1] != entry:
            deduped.append(entry)
    return deduped


def _parse_reg_dump(cli_text: str, addr: int) -> int | None:
    """Return the register value gpsim printed for `reg(0x...)`.

    gpsim prints one of these shapes when the script issues `reg(0xN)`:
      baudcon[0xfb8] = 0x48
      INVREG_F98[0xf98] = 0x0
    """
    pat = re.compile(
        rf"\w+\[0x{addr:x}\]\s*=\s*0x([0-9A-Fa-f]+)\b",
        re.IGNORECASE,
    )
    m = pat.search(cli_text)
    if m:
        return int(m.group(1), 16) & 0xFF
    return None


def run_gpsim_probe(
    main_hex: Path,
    break_pc: int,
    *,
    out_dir: Path,
) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "probe_baudcon.log"
    if log_path.exists():
        log_path.unlink()
    bootstrap_stc = out_dir / "probe_baudcon_an0.stc"
    write_main_an0_bootstrap_stc(bootstrap_stc, processor=PROCESSOR)
    stc = _build_probe_stc(
        out_dir,
        main_hex,
        log_path,
        bootstrap_stc,
        break_pc=break_pc,
        fallback_cycles=GPSIM_RUN_CYCLES,
    )

    binary = resolve_gpsim_binary(required=True)
    cp = subprocess.run(
        [binary, "-i", "-c", str(stc)],
        text=True,
        capture_output=True,
        check=False,
    )
    cli = cp.stdout + cp.stderr
    (out_dir / "probe_baudcon.cli").write_text(cli, encoding="utf-8")
    if cp.returncode != 0:
        raise RuntimeError(
            f"gpsim exited {cp.returncode}; see {out_dir}/probe_baudcon.cli"
        )

    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    # gpsim auto-prints `log w` events to stdout in addition to the log
    # file; if `log off` runs after the breakpoint we still get the event
    # in cli text.  Parse both and merge.
    writes = _parse_baudcon_writes(log_text + "\n" + cli)
    return {
        "stc": stc,
        "log_path": log_path,
        "cli": cli,
        "log_text": log_text,
        "writes": writes,
        "reg_fb8": _parse_reg_dump(cli, 0xFB8),
        "reg_f98": _parse_reg_dump(cli, 0xF98),
        "exec_break_hit": ("hit a breakpoint" in cli.lower()),
    }


def main(argv: Iterable[str]) -> int:
    main_hex = Path(V32_MAIN_HEX)
    if not main_hex.exists():
        print(f"V3.2 MAIN hex missing at {main_hex}", file=sys.stderr)
        return 2

    print(f"=== probe: V3.2 MAIN hex {main_hex.name} ===")
    fb8_addr, f98_addr = static_check(main_hex)
    print(f"  static: signature 'movlw 0x48; movwf BAUDCON@FB8' "
          f"-> {f'0x{fb8_addr:04X}' if fb8_addr is not None else 'absent'}")
    print(f"  static: signature 'movlw 0x48; movwf BAUDCON@F98' "
          f"-> {f'0x{f98_addr:04X}' if f98_addr is not None else 'absent'}")

    if fb8_addr is None:
        print(
            "FAIL: V3.2 hex does not contain the FB8-form BAUDCON write opcode "
            "0E48 6EB8 -- aborting probe.",
            file=sys.stderr,
        )
        return 3
    if f98_addr is not None:
        print(
            "FAIL: V3.2 hex contains the F98-form BAUDCON write opcode "
            "(0E48 6E98); the static premise of the probe is invalid.",
            file=sys.stderr,
        )
        return 3

    binary = resolve_gpsim_binary()
    if binary is None:
        print(
            "WARN: gpsim binary not found on PATH; skipping live probe.\n"
            "  set DLCP_GPSIM_BIN or run scripts/gpsim-xtc once to compile.\n"
            "  static check alone proves the firmware writes BAUDCON at\n"
            "  0xFB8 (the FB8-form 'movwf' opcode is present) and never\n"
            "  at 0xF98 (the F98-form opcode is absent), but does not\n"
            "  observe gpsim's runtime mapping."
        )
        _print_verdict(static_only=True, reg_fb8=None, reg_f98=None, writes=[])
        return 0

    print(f"  gpsim: {binary}")
    # Break right after the `movwf BAUDCON, ACCESS` instruction (4 bytes
    # past the start of the 'movlw 0x48; movwf BAUDCON' pair).
    break_pc = (fb8_addr + 4) & 0xFFFF
    print(f"  gpsim: breaking at PC=0x{break_pc:04X} (post-BAUDCON-write)")

    with tempfile.TemporaryDirectory(prefix="probe_baudcon_") as tdp:
        out_dir = Path(tdp)
        result = run_gpsim_probe(main_hex, break_pc=break_pc, out_dir=out_dir)
        writes = result["writes"]  # type: ignore[assignment]
        reg_fb8 = result["reg_fb8"]  # type: ignore[assignment]
        reg_f98 = result["reg_f98"]  # type: ignore[assignment]
        print(f"  gpsim: baudcon writes captured: {writes!r}")
        print(f"  gpsim: reg(0xFB8) post-run: "
              f"{f'0x{reg_fb8:02X}' if reg_fb8 is not None else 'unknown'}")
        print(f"  gpsim: reg(0xF98) post-run: "
              f"{f'0x{reg_f98:02X}' if reg_f98 is not None else 'unknown'}")

        # Strict pass conditions: a 0x48 write to baudcon(0xFB8), residue
        # 0x48 at 0xFB8, and 0x00 at 0xF98.  Each is necessary; together
        # they leave no false-positive path for the verdict.
        failures: list[str] = []
        if not writes:
            failures.append("no BAUDCON writes captured by gpsim")
        elif not any(v == 0x48 and addr == 0xFB8 for _, v, addr in writes):
            failures.append(
                "gpsim did not log a 0x48 write to baudcon at address "
                f"0x0FB8 (got {writes!r})"
            )
        if reg_fb8 is None:
            failures.append("could not parse reg(0xFB8) from gpsim CLI")
        elif reg_fb8 != 0x48:
            failures.append(
                f"reg(0xFB8) post-run = 0x{reg_fb8:02X} (expected 0x48)"
            )
        if reg_f98 is None:
            failures.append("could not parse reg(0xF98) from gpsim CLI")
        elif reg_f98 != 0x00:
            failures.append(
                f"reg(0xF98) post-run = 0x{reg_f98:02X} "
                "(expected 0x00 since gpsim's 2455 model leaves F98 unmapped)"
            )

        if failures:
            (REPO_ROOT / "artifacts" / "sim_rewrite_divergences").mkdir(
                parents=True, exist_ok=True
            )
            div_dir = REPO_ROOT / "artifacts" / "sim_rewrite_divergences"
            shutil.copy(out_dir / "probe_baudcon.cli",
                        div_dir / "P0.0__probe_baudcon.cli")
            if result["log_path"].exists():
                shutil.copy(result["log_path"],
                            div_dir / "P0.0__probe_baudcon.log")
            print("FAIL: live probe assertions did not all hold:",
                  file=sys.stderr)
            for msg in failures:
                print(f"  - {msg}", file=sys.stderr)
            print(f"  log:  {div_dir / 'P0.0__probe_baudcon.log'}",
                  file=sys.stderr)
            print(f"  cli:  {div_dir / 'P0.0__probe_baudcon.cli'}",
                  file=sys.stderr)
            return 4

        _print_verdict(
            static_only=False,
            reg_fb8=reg_fb8,
            reg_f98=reg_f98,
            writes=writes,
        )
    return 0


def _print_verdict(
    *,
    static_only: bool,
    reg_fb8: int | None,
    reg_f98: int | None,
    writes: list[tuple[int, int, int]],
) -> None:
    print()
    print("=== verdict ===")
    print("  Static (always checked): the V3.2 MAIN hex contains the")
    print("  FB8-form 'movwf BAUDCON' opcode 6EB8 and not the F98-form")
    print("  6E98 — the assembled firmware writes BAUDCON to 0xFB8.")
    if static_only:
        print("  Live (skipped): gpsim binary not available; the static")
        print("  evidence alone is conclusive on the firmware side but")
        print("  does not exercise gpsim's runtime SFR map.")
    else:
        addrs = sorted({addr for _, _, addr in writes})
        kinds = sorted({v for _, v, _ in writes})
        print(f"  Live: gpsim observed {len(writes)} write(s) to baudcon "
              f"at address(es) {[f'0x{a:04X}' for a in addrs]!r} "
              f"with values {kinds!r}; reg(0xFB8)="
              f"{f'0x{reg_fb8:02X}' if reg_fb8 is not None else '?'}, "
              f"reg(0xF98)="
              f"{f'0x{reg_f98:02X}' if reg_f98 is not None else '?'}.")
        print("  All assertions held: 0x48 written to baudcon at 0xFB8;")
        print("  reg(0xFB8) reads 0x48; reg(0xF98) reads 0x00 (unmapped).")
    print()
    print("  Resolution of §11b open question:")
    print("    None of the three hypothesised explanations (a/b/c) apply as")
    print("    stated.  The §11b premise — 'datasheet places BAUDCON at")
    print("    0xF98' — is itself incorrect and arose from misreading the")
    print("    PDF→markdown rendering of DS39632E Table 5-1 in")
    print("    firmware/reference/39632e.md.  The data rows of that table")
    print("    (e.g. line 2708: '|TBLPTRU|STATUS|BAUDCON|—|UEP8|') agree")
    print("    with gputils' p18f2455.inc:")
    print("      BAUDCON  EQU  H'0FB8'   STATUS  EQU  H'0FD8'")
    if static_only:
        print("    The PDF column-header text contains a +0x20 mis-alignment")
        print("    that the markdown converter preserved verbatim, but the")
        print("    gputils header and the assembled V3.2 hex (this run's")
        print("    static evidence) agree on 0xFB8.  This run did NOT")
        print("    exercise gpsim's runtime SFR map, so the gpsim portion")
        print("    of the resolution is on file from prior live runs and")
        print("    in spec §11b — re-run with gpsim available to re-confirm.")
    else:
        print("    The PDF column-header text contains a +0x20 mis-alignment")
        print("    that the markdown converter preserved verbatim, but neither")
        print("    the gputils header, gpsim's 2455 SFR map (this run), nor")
        print("    the assembled V3.2 hex agree with the F98 reading.")
    print()
    print("  Implication for the Rust port: BAUDCON for the 2455 is mapped")
    print("  at 0xFB8 (matching gpsim, gputils, and the assembled firmware).")
    print("  Spec §6 (peripheral table), §11 (risk register), and §11b have")
    print("  been updated to record this resolution.")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
