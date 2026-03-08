"""Strict instruction-level cmd=0x03 regression checks for MAIN firmware."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from dlcp_fw.paths import STOCK_MAIN_HEX
from dlcp_fw.sim.hexio import parse_intel_hex
from dlcp_fw.sim.main_gpsim import run_main_cmd03_dispatch_gpsim
from dlcp_fw.sim.manifests import main_i2c_bypass, main_reset_to_appstart, main_serial_mailbox_hooks
from dlcp_fw.sim.overlay import apply_overlays


def _require_gpsim() -> None:
    if shutil.which("gpsim") is None:
        pytest.skip("gpsim not installed")


def _filename_slot_bytes(regs: dict[int, int]) -> bytes:
    return bytes(regs.get(addr, 0xFF) & 0xFF for addr in range(0x2C0, 0x2DE))


def _protected_sentinels() -> dict[int, int]:
    return {
        0x05E: 0xA5,
        0x073: 0x5A,
        0x074: 0xC3,
        0x099: 0x12,
        0x0A5: 0x21,
        0x0A6: 0x22,
        0x0A7: 0x23,
        0x0A8: 0x24,
        0x0A9: 0x25,
        0x0AA: 0x26,
        0x0B2: 0x31,
        0x0B3: 0x32,
        0x0B8: 0x33,
    }


@pytest.mark.gpsim
@pytest.mark.slow
def test_cmd03_subcmd09_hits_label003_and_preserves_preset_related_ram(patched_main_hex) -> None:
    _require_gpsim()
    sentinels = _protected_sentinels()
    payload = b"TEST\x00"

    stock = run_main_cmd03_dispatch_gpsim(
        subcmd=0x09,
        payload=payload,
        main_hex=STOCK_MAIN_HEX,
        sentinel_regs=sentinels,
    )
    patched = run_main_cmd03_dispatch_gpsim(
        subcmd=0x09,
        payload=payload,
        main_hex=patched_main_hex,
        sentinel_regs=sentinels,
    )

    for res in (stock, patched):
        assert res.parser_break_hit is True
        assert res.label003_break_hit is True
        assert res.return_break_hit is True
        slot = _filename_slot_bytes(res.regs)
        assert slot[:4] == b"TEST"
        assert slot[4] == 0xFF
        assert set(slot[4:]) == {0xFF}
        assert res.regs.get(0x097) == 0x09
        for addr, want in sentinels.items():
            assert res.regs.get(addr) == want

    compare_regs = sorted(set(sentinels) | set(range(0x2C0, 0x2DE)) | {0x097, 0x0BD, 0x0C0})
    assert {a: stock.regs.get(a) for a in compare_regs} == {
        a: patched.regs.get(a) for a in compare_regs
    }


@pytest.mark.gpsim
@pytest.mark.slow
def test_cmd03_subcmd0a_erases_filename_slot_without_touching_preset_related_ram(
    patched_main_hex,
) -> None:
    _require_gpsim()
    sentinels = _protected_sentinels()
    for i in range(0x1E):
        sentinels[0x2C0 + i] = (0x40 + i) & 0xFF

    res = run_main_cmd03_dispatch_gpsim(
        subcmd=0x0A,
        payload=b"",
        main_hex=patched_main_hex,
        sentinel_regs=sentinels,
    )

    assert res.parser_break_hit is True
    assert res.label003_break_hit is True
    assert res.return_break_hit is True
    assert _filename_slot_bytes(res.regs) == bytes([0xFF] * 0x1E)
    assert res.regs.get(0x097) == 0x0A
    for addr, want in _protected_sentinels().items():
        assert res.regs.get(addr) == want


def test_cmd03_handler_bytes_match_stock_without_filename_hooks(patched_main_hex) -> None:
    stock = parse_intel_hex(STOCK_MAIN_HEX)
    patched = parse_intel_hex(patched_main_hex)

    for addr in range(0x10D0, 0x1132 + 1):
        assert patched.get(addr, 0xFF) == stock.get(addr, 0xFF)

    for hook in (0x20BE, 0x27C0):
        stock_bytes = [stock.get(hook + i, 0xFF) for i in range(4)]
        patched_bytes = [patched.get(hook + i, 0xFF) for i in range(4)]
        assert patched_bytes == stock_bytes, f"unexpected cmd03 hook at 0x{hook:04X}"


def _run_cmd03_persist_probe(*, main_hex: Path, subcmd: int, payload: bytes) -> list[tuple[int, int]]:
    with tempfile.TemporaryDirectory(prefix="main_cmd03_eeprom_probe_") as td:
        tdp = Path(td)
        sim_hex = tdp / "sim.hex"
        log_path = tdp / "run.log"
        stc_path = tdp / "run.stc"

        apply_overlays(
            main_hex,
            sim_hex,
            manifests=[main_reset_to_appstart(), main_i2c_bypass(), main_serial_mailbox_hooks()],
        )

        data = bytes(payload[:30])
        lines = ["processor p18f2550", f"load {sim_hex}", "break e 0x1BEA", "run"]
        for i in range(30):
            lines.append(f"reg(0x{(0x11C + i):03x})=0x00")
        for i, b in enumerate(data):
            lines.append(f"reg(0x{(0x11C + i):03x})=0x{b:02X}")
        lines.extend(
            [
                "reg(0x11a)=0x03",
                f"reg(0x11b)=0x{subcmd & 0xFF:02X}",
                "reg(0x0c0)=0x01",
                "pc=0x3A7E",
                "break e 0x10D0",
                "run",
                "break e 0x15AA",
                "run",
                "reg(0x0bd)=0x20",
                "reg(0x07e)=0x01",
                f"log on {log_path}",
                "log w eeadr",
                "log w eedata",
                "pc=0x265C",
                "break e 0x27EC",
                "run",
                "log off",
                "quit",
                "",
            ]
        )
        stc_path.write_text("\n".join(lines), encoding="ascii")

        cp = subprocess.run(
            ["gpsim", "-i", "-c", str(stc_path)],
            text=True,
            capture_output=True,
            check=False,
            timeout=90.0,
        )
        cli = cp.stdout + cp.stderr
        if cp.returncode != 0:
            raise RuntimeError(f"gpsim cmd03 EEPROM probe failed ({cp.returncode}):\n{cli}")
        assert "line_10d0(0x10d0)" in cli.lower()
        assert "line_27ec(0x27ec)" in cli.lower()

        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        addr_re = re.compile(r"Wr(?:ite|ote):\s+0x([0-9A-Fa-f]+)\s+to eeadr\(", re.IGNORECASE)
        data_re = re.compile(r"Wr(?:ite|ote):\s+0x([0-9A-Fa-f]+)\s+to eedata\(", re.IGNORECASE)

        writes: list[tuple[int, int]] = []
        last_addr: int | None = None
        for line in log_text.splitlines():
            m_addr = addr_re.search(line)
            if m_addr:
                last_addr = int(m_addr.group(1), 16) & 0xFF
                continue
            m_data = data_re.search(line)
            if m_data and last_addr is not None:
                data = int(m_data.group(1), 16) & 0xFF
                writes.append((last_addr, data))
                last_addr = None
        return writes


@pytest.mark.gpsim
@pytest.mark.slow
def test_cmd03_persist_remains_stock_parity_without_generation_sideband(patched_main_hex) -> None:
    _require_gpsim()
    payload = bytes((i + 1) & 0xFF for i in range(30))

    stock_writes = _run_cmd03_persist_probe(main_hex=STOCK_MAIN_HEX, subcmd=0x09, payload=payload)
    patched_writes = _run_cmd03_persist_probe(main_hex=patched_main_hex, subcmd=0x09, payload=payload)

    expected_addrs = set(range(0x60, 0x7E))
    stock_addrs = [a for a, _ in stock_writes]
    patched_addrs = [a for a, _ in patched_writes]
    assert stock_addrs and set(stock_addrs).issubset(expected_addrs)
    assert patched_addrs and set(patched_addrs).issubset(expected_addrs)
    assert expected_addrs.issubset(set(stock_addrs))
    assert expected_addrs.issubset(set(patched_addrs))
    assert 0x7E not in set(patched_addrs)

    def last_value_per_addr(writes: list[tuple[int, int]]) -> dict[int, int]:
        out: dict[int, int] = {}
        for addr, data in writes:
            out[addr] = data
        return out

    stock_last = last_value_per_addr(stock_writes)
    patched_last = last_value_per_addr(patched_writes)
    for addr in range(0x60, 0x7E):
        assert patched_last.get(addr) == stock_last.get(addr)
