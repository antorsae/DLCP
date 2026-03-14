"""Strict instruction-level cmd=0x03 regression checks for MAIN firmware."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import pytest

from dlcp_fw.paths import STOCK_MAIN_HEX
from dlcp_fw.sim.gpsim import gpsim_available, require_gpsim_binary
from dlcp_fw.sim.hexio import parse_intel_hex
from dlcp_fw.sim.main_gpsim import build_seeded_main_sim_hex, run_main_cmd03_dispatch_gpsim
from dlcp_fw.sim.manifests import main_reset_to_appstart, main_serial_mailbox_hooks
from dlcp_fw.sim.overlay import apply_overlays


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _fixture_hex(request: pytest.FixtureRequest, fixture_name: str) -> Path:
    return request.getfixturevalue(fixture_name)


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
@pytest.mark.parametrize(
    "patched_fixture",
    [
        pytest.param("patched_main_hex_v24", id="v24"),
        pytest.param("patched_main_hex", id="v25"),
    ],
)
def test_cmd03_subcmd09_hits_label003_and_preserves_preset_related_ram(
    request: pytest.FixtureRequest,
    patched_fixture: str,
) -> None:
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
        main_hex=_fixture_hex(request, patched_fixture),
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
@pytest.mark.parametrize(
    "patched_fixture",
    [
        pytest.param("patched_main_hex_v24", id="v24"),
        pytest.param("patched_main_hex", id="v25"),
    ],
)
def test_cmd03_subcmd0a_erases_filename_slot_without_touching_preset_related_ram(
    request: pytest.FixtureRequest,
    patched_fixture: str,
) -> None:
    _require_gpsim()
    sentinels = _protected_sentinels()
    for i in range(0x1E):
        sentinels[0x2C0 + i] = (0x40 + i) & 0xFF

    res = run_main_cmd03_dispatch_gpsim(
        subcmd=0x0A,
        payload=b"",
        main_hex=_fixture_hex(request, patched_fixture),
        sentinel_regs=sentinels,
    )

    assert res.parser_break_hit is True
    assert res.label003_break_hit is True
    assert res.return_break_hit is True
    assert _filename_slot_bytes(res.regs) == bytes([0xFF] * 0x1E)
    assert res.regs.get(0x097) == 0x0A
    for addr, want in _protected_sentinels().items():
        assert res.regs.get(addr) == want


@pytest.mark.parametrize(
    "patched_fixture",
    [
        pytest.param("patched_main_hex_v24", id="v24"),
        pytest.param("patched_main_hex", id="v25"),
    ],
)
def test_cmd03_handler_body_matches_stock_but_filename_windows_are_patched(
    request: pytest.FixtureRequest,
    patched_fixture: str,
) -> None:
    stock = parse_intel_hex(STOCK_MAIN_HEX)
    patched = parse_intel_hex(_fixture_hex(request, patched_fixture))

    for addr in range(0x10D0, 0x1132 + 1):
        assert patched.get(addr, 0xFF) == stock.get(addr, 0xFF)

    assert [patched.get(0x20BE + i, 0xFF) for i in range(4)] == [0x01, 0xD8, 0x11, 0xD0]
    assert [patched.get(0x20C2 + i, 0xFF) for i in range(8)] == [0x60, 0x0E, 0x5E, 0xB4, 0x83, 0x0E, 0x0A, 0x6E]
    assert [patched.get(0x27C0 + i, 0xFF) for i in range(8)] == [0x60, 0x0E, 0x5E, 0xB4, 0x83, 0x0E, 0x0A, 0x6E]


def _run_cmd03_persist_probe(
    *,
    main_hex: Path,
    subcmd: int,
    payload: bytes,
    preset_idx: int = 0,
) -> list[tuple[int, int]]:
    with tempfile.TemporaryDirectory(prefix="main_cmd03_eeprom_probe_") as td:
        tdp = Path(td)
        seeded_hex = tdp / "seeded.hex"
        sim_hex = tdp / "sim.hex"
        log_path = tdp / "run.log"
        stc_path = tdp / "run.stc"

        build_seeded_main_sim_hex(main_hex, seeded_hex)
        apply_overlays(
            seeded_hex,
            sim_hex,
            manifests=[main_reset_to_appstart(), main_serial_mailbox_hooks()],
        )

        data = bytes(payload[:30])
        preset_bit = 0x04 if preset_idx else 0x00
        lines = ["processor p18f2455", f"load {sim_hex}", "break e 0x1BEA", "run"]
        for i in range(30):
            lines.append(f"reg(0x{(0x11C + i):03x})=0x00")
        for i, b in enumerate(data):
            lines.append(f"reg(0x{(0x11C + i):03x})=0x{b:02X}")
        lines.extend(
            [
                f"reg(0x05e)=0x{preset_bit:02X}",
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
                "break e 0x27EA",
                "run",
                "log off",
                "quit",
                "",
            ]
        )
        stc_path.write_text("\n".join(lines), encoding="ascii")
        gpsim_bin = require_gpsim_binary()

        cp = subprocess.run(
            [gpsim_bin, "-i", "-c", str(stc_path)],
            text=True,
            capture_output=True,
            check=False,
            timeout=90.0,
        )
        cli = cp.stdout + cp.stderr
        if cp.returncode != 0:
            raise RuntimeError(f"gpsim cmd03 EEPROM probe failed ({cp.returncode}):\n{cli}")
        assert "line_10d0(0x10d0)" in cli.lower()
        assert "line_27ea(0x27ea)" in cli.lower()

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
@pytest.mark.parametrize(
    ("patched_fixture", "preset_idx", "expected_addrs"),
    [
        pytest.param("patched_main_hex_v24", 0, set(range(0x60, 0x7E)), id="v24_a"),
        pytest.param("patched_main_hex_v24", 1, set(range(0x83, 0xA1)), id="v24_b"),
        pytest.param("patched_main_hex", 0, set(range(0x60, 0x7E)), id="v25_a"),
        pytest.param("patched_main_hex", 1, set(range(0x83, 0xA1)), id="v25_b"),
    ],
)
def test_cmd03_persist_writes_active_slot_without_generation_sideband(
    request: pytest.FixtureRequest,
    patched_fixture: str,
    preset_idx: int,
    expected_addrs: set[int],
) -> None:
    _require_gpsim()
    payload = bytes((i + 1) & 0xFF for i in range(30))

    writes = _run_cmd03_persist_probe(
        main_hex=_fixture_hex(request, patched_fixture),
        subcmd=0x09,
        payload=payload,
        preset_idx=preset_idx,
    )

    addrs = [a for a, _ in writes]
    assert addrs and set(addrs).issubset(expected_addrs)
    assert expected_addrs.issubset(set(addrs))
    assert 0x7E not in set(addrs)
    assert 0xA1 not in set(addrs)

    last: dict[int, int] = {}
    for addr, data in writes:
        last[addr] = data
    expected_base = min(expected_addrs)
    for i in range(30):
        assert last.get(expected_base + i) == payload[i]
