"""gpsim execution helpers."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


class GpsimError(RuntimeError):
    """gpsim run failed."""


@dataclass(frozen=True)
class GpsimRunConfig:
    hex_path: Path
    cycles: int
    watch_writes: Sequence[str] = field(
        default_factory=lambda: ("porta", "portb", "trisa", "trisb", "lata", "latb")
    )
    break_expr: str | None = None


@dataclass(frozen=True)
class GpsimRunResult:
    stc_path: Path
    cli_path: Path
    log_path: Path
    stdout: str
    stderr: str

    @property
    def cli_text(self) -> str:
        return self.stdout + self.stderr


def _build_script(cfg: GpsimRunConfig, stc_path: Path, log_path: Path) -> None:
    lines = [
        "processor p18f2550",
        f"load {cfg.hex_path}",
        f"log on {log_path}",
    ]
    for reg in cfg.watch_writes:
        lines.append(f"log w {reg}")
    if cfg.break_expr:
        lines.append(f"break e {cfg.break_expr}")
    else:
        lines.append(f"break c {cfg.cycles}")
    lines.extend(
        [
            "run",
            "log off",
            "quit",
            "",
        ]
    )
    stc_path.write_text("\n".join(lines), encoding="ascii")


def run_gpsim(cfg: GpsimRunConfig, out_dir: Path) -> GpsimRunResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    stc = out_dir / "run.stc"
    log_path = out_dir / "gpsim.log"
    cli_path = out_dir / "gpsim_cli.txt"
    _build_script(cfg, stc, log_path)

    cp = subprocess.run(
        ["gpsim", "-i", "-c", str(stc)],
        text=True,
        capture_output=True,
        check=False,
    )
    cli_text = cp.stdout + cp.stderr
    cli_path.write_text(cli_text, encoding="utf-8")
    if cp.returncode != 0:
        raise GpsimError(f"gpsim exited with {cp.returncode}: see {cli_path}")
    if not cfg.break_expr and "cycle break:" not in cli_text:
        raise GpsimError(f"gpsim did not hit cycle break: see {cli_path}")
    return GpsimRunResult(
        stc_path=stc,
        cli_path=cli_path,
        log_path=log_path,
        stdout=cp.stdout,
        stderr=cp.stderr,
    )
