from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile

import pytest

from dlcp_fw.sim.gpsim import gpsim_available, require_gpsim_binary
from dlcp_fw.sim.hexio import parse_intel_hex, write_intel_hex
from dlcp_fw.sim.main_gpsim import build_seeded_main_sim_hex
from dlcp_fw.sim.manifests import main_reset_to_appstart, main_serial_mailbox_hooks
from dlcp_fw.sim.overlay import apply_overlays


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _fixture_hex(request: pytest.FixtureRequest, fixture_name: str) -> Path:
    return request.getfixturevalue(fixture_name)


def _encode_slot(name: str) -> bytes:
    raw = name.encode("ascii", errors="ignore")[:30]
    return raw + (b"\xFF" * (30 - len(raw)))


def _decode_slot(regs: dict[int, int]) -> str:
    chars = []
    for addr in range(0x2C0, 0x2DE):
        b = regs.get(addr, 0xFF) & 0xFF
        if b in (0x00, 0xFF):
            break
        chars.append(chr(b))
    return "".join(chars)


def _parse_regs(cli_text: str) -> dict[int, int]:
    import re

    p = re.compile(r"REG([0-9A-Fa-f]{3})\[0x([0-9A-Fa-f]+)\]\s*=\s*0x([0-9A-Fa-f]+)")
    out: dict[int, int] = {}
    for line in cli_text.splitlines():
        m = p.search(line)
        if m:
            out[int(m.group(2), 16)] = int(m.group(3), 16)
    return out


def _make_seeded_filename_hex(
    *,
    base_hex: Path,
    tmp_path: Path,
    name_a: str,
    name_b: str,
) -> Path:
    seeded = tmp_path / "main_seeded.hex"
    out_hex = tmp_path / "main_filename_seeded.hex"
    build_seeded_main_sim_hex(base_hex, seeded)
    mem = parse_intel_hex(seeded)
    for i, b in enumerate(_encode_slot(name_a)):
        mem[0xF00060 + i] = b
    for i, b in enumerate(_encode_slot(name_b)):
        mem[0xF00083 + i] = b
    write_intel_hex(out_hex, mem)
    return out_hex


def _run_cmd20_dispatch_gpsim(*, main_hex: Path, data: int) -> dict[int, int]:
    with tempfile.TemporaryDirectory(prefix="main_cmd20_dispatch_") as td:
        tdp = Path(td)
        seeded_hex = tdp / "main_seeded.hex"
        sim_hex = tdp / "main_sim.hex"
        stc_path = tdp / "run.stc"

        build_seeded_main_sim_hex(main_hex, seeded_hex)
        apply_overlays(
            seeded_hex,
            sim_hex,
            manifests=[main_reset_to_appstart(), main_serial_mailbox_hooks()],
        )

        watch_regs = [0x05E]
        watch_regs.extend(range(0x2C0, 0x2DE))
        lines = [
            "processor p18f2455",
            f"load {sim_hex}",
            "break e 0x1BEA",
            "run",
            "reg(0x0a2)=0x20",
            f"reg(0x0a3)=0x{data & 0xFF:02X}",
            "break e 0x1E6C",
            "pc=0x1E2E",
            "run",
        ]
        for addr in watch_regs:
            lines.append(f"reg(0x{addr:03x})")
        lines.extend(["quit", ""])
        stc_path.write_text("\n".join(lines), encoding="ascii")

        cp = subprocess.run(
            [require_gpsim_binary(), "-i", "-c", str(stc_path)],
            text=True,
            capture_output=True,
            check=False,
            timeout=30.0,
        )
        cli_text = cp.stdout + cp.stderr
        if cp.returncode != 0:
            raise RuntimeError(f"gpsim cmd20 dispatch failed ({cp.returncode}):\n{cli_text}")
        assert "line_1e6c(0x1e6c)" in cli_text.lower()
        return _parse_regs(cli_text)


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    "main_hex_fixture",
    [
        pytest.param("patched_main_hex_v24", id="v24"),
        pytest.param("patched_main_hex", id="v25"),
    ],
)
def test_cmd20_dispatch_switches_live_filename_ram_between_a_and_b(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    main_hex_fixture: str,
) -> None:
    _require_gpsim()
    fixture_hex = _make_seeded_filename_hex(
        base_hex=_fixture_hex(request, main_hex_fixture),
        tmp_path=tmp_path,
        name_a="ALPHA-A",
        name_b="BRAVO-B",
    )

    regs_to_b = _run_cmd20_dispatch_gpsim(main_hex=fixture_hex, data=0x01)
    assert _decode_slot(regs_to_b) == "BRAVO-B"

    regs_to_a = _run_cmd20_dispatch_gpsim(main_hex=fixture_hex, data=0x00)
    assert _decode_slot(regs_to_a) == "ALPHA-A"
