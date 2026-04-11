"""Recovered-table DSP apply regression for stock/V2.7/V3.1.

This test uses the recovered V2.3 combined seed as the source of truth for a
real non-stock DSP table. It bypasses the slow boot/service-loop path and
enters the stock per-entry apply helper directly:

  main_i2c_service_381c: flash entry -> TAS3108 I2C write

That gives a much higher-fidelity regression than the generic post-boot
`dsp34` register snapshot, and it avoids the false overwrite artifacts caused
by flattening overlapping TAS3108 register windows into a simple linear
regfile.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pytest

from dlcp_fw.paths import (
    PATCHED_MAIN_HEX_V27,
    STOCK_MAIN_COMBINED_HEX,
    STOCK_MAIN_HEX,
    V31_MAIN_HEX,
)
from dlcp_fw.sim.gpsim import gpsim_available, require_gpsim_binary
from dlcp_fw.sim.hexio import parse_intel_hex, write_intel_hex
from dlcp_fw.sim.main_gpsim import (
    MAIN_GPSIM_PROCESSOR,
    MainI2CRegFileDevice,
    build_seeded_main_sim_hex,
    write_main_an0_bootstrap_stc,
    write_main_i2c_regfile_stc,
)
from dlcp_fw.sim.manifests import main_reset_to_appstart
from dlcp_fw.sim.overlay import apply_overlays
from dlcp_fw.sim.v30_symbols import find_code_signature, parse_gpasm_symbols

_EXEC_BREAK_RE = re.compile(r"Execution at .*?\(0x([0-9a-f]{4})\)", re.IGNORECASE)
_REGFILE_RE = re.compile(
    r"(?:[A-Za-z0-9_]+\.)?reg([0-9A-Fa-f]{2})\s*=\s*(?:\$|0x)([0-9A-Fa-f]+)",
    re.IGNORECASE,
)
_SFR_RE = re.compile(r"\[0x([0-9A-Fa-f]+)\]\s*=\s*0x([0-9A-Fa-f]+)")

_PARSER_IDLE_SIG = bytes.fromhex("39ec24f0000901e144d1fdec22f0")
_HID_DISPATCH_ENTRY_SIG = bytes.fromhex("e8cf57f021eeedf010ee4df0070edecf")
_HID_DISPATCH_RETURN_SIG = bytes.fromhex("01011a6b12001a0e5824d96eda6a010e")
_ENTRY_APPLY_SIG = bytes.fromhex("13c003f014c004f0056a066a086a040e076e0a6a170e096e")
_ENTRY_BUFFER_READY_SIG = bytes.fromhex("c580c5b0fed7680e34ec1ff02f5034ec")
_ENTRY_RETURN_WINDOW_SIG = bytes.fromhex("c584c5b4fed7120041c039f042c03af0")

# Synthetic HID chunk injection windows captured from the recovered 0x5600
# page on stock V2.3. These are the exact page-buffer windows after chunk 0 and
# chunk 1 are injected while the slot-0x37 payload bytes in flash are
# pre-zeroed. V2.7 and V3.1 must preserve the matching stock shape.
_RECOVERED_UPLOAD_BUFFER_WINDOW_CMD07 = bytes.fromhex(
    "000000000137140000000fe7d540003a3f7c0f888b20003e69f10fe601381400005a"
)
_RECOVERED_UPLOAD_BUFFER_WINDOW_CMD080C = bytes.fromhex(
    "00000000100008f000000fe7d540003a3f7c0f888b20003e69f10fe6ffffffffffff"
)

# Selected recovered combined-table entries: early, middle, late, and commit.
_RECOVERED_ENTRY_FIXTURES: tuple[tuple[int, bytes], ...] = (
    (0x37, bytes.fromhex("0fe7d540003a3f7c0f888b20003e69f10fe61ac7")),
    (0x55, bytes.fromhex("0f989b3100b041190fa7e58400ddb1e60f8f1d87")),
    (0x82, bytes.fromhex("0040034c0f805944003fa80700feb3030f8143d5")),
    (0xD4, bytes.fromhex("00000001")),
)

_FIRMWARE_CASES = (
    pytest.param(STOCK_MAIN_HEX, id="v23_seeded"),
    pytest.param(PATCHED_MAIN_HEX_V27, id="v27"),
    pytest.param(V31_MAIN_HEX, id="v31"),
)
_UPLOAD_BUFFER_CASES = (
    pytest.param(STOCK_MAIN_HEX, id="v23_seeded"),
    pytest.param(PATCHED_MAIN_HEX_V27, id="v27"),
    pytest.param(V31_MAIN_HEX, id="v31"),
)
_UPLOAD_CMD_CASES = (
    pytest.param(0x07, _RECOVERED_UPLOAD_BUFFER_WINDOW_CMD07, 0x5600, id="cmd07"),
    pytest.param(0x08, _RECOVERED_UPLOAD_BUFFER_WINDOW_CMD080C, 0x0000, id="cmd08"),
    pytest.param(0x09, _RECOVERED_UPLOAD_BUFFER_WINDOW_CMD080C, 0x0000, id="cmd09"),
    pytest.param(0x0A, _RECOVERED_UPLOAD_BUFFER_WINDOW_CMD080C, 0x0000, id="cmd0a"),
    pytest.param(0x0B, _RECOVERED_UPLOAD_BUFFER_WINDOW_CMD080C, 0x0000, id="cmd0b"),
    pytest.param(0x0C, _RECOVERED_UPLOAD_BUFFER_WINDOW_CMD080C, 0x0000, id="cmd0c"),
)
_STALE_UPLOAD_CHUNK_OFFSET = 0x90
_STALE_UPLOAD_PAGE_BASE = 0x3412


@dataclass(frozen=True)
class _UploadBufferProbeResult:
    page_buffer_window: bytes
    flash_page_base: int
    page_chunk_offset: int


@dataclass(frozen=True)
class _ProbePcs:
    parser_idle_pc: int
    hid_dispatch_entry_pc: int
    hid_dispatch_return_pc: int


@dataclass(frozen=True)
class _EntryApplyPcs:
    entry_apply_pc: int
    entry_buffer_ready_pc: int
    entry_apply_return_pc: int


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


@lru_cache(maxsize=None)
def _resolve_v31_probe_pcs(lst_path: Path) -> _ProbePcs:
    symbols = parse_gpasm_symbols(lst_path)
    return _ProbePcs(
        parser_idle_pc=symbols["flow_main_uart_service_1be6_1bea"],
        hid_dispatch_entry_pc=symbols["hid_command_dispatch"],
        hid_dispatch_return_pc=symbols["flow_hid_command_dispatch_15aa"],
    )


def _resolve_probe_pcs(main_hex: Path) -> _ProbePcs:
    if main_hex == V31_MAIN_HEX:
        lst_path = main_hex.with_suffix(".lst")
        if not lst_path.exists():
            raise AssertionError(f"missing gpasm listing for {main_hex.name}: {lst_path}")
        return _resolve_v31_probe_pcs(lst_path)
    parser_idle_pc = find_code_signature(main_hex, _PARSER_IDLE_SIG)
    hid_dispatch_entry_pc = find_code_signature(main_hex, _HID_DISPATCH_ENTRY_SIG)
    hid_dispatch_return_pc = find_code_signature(main_hex, _HID_DISPATCH_RETURN_SIG)
    if (
        parser_idle_pc is None
        or hid_dispatch_entry_pc is None
        or hid_dispatch_return_pc is None
    ):
        raise AssertionError(f"{main_hex.name}: failed to resolve stock-equivalent probe PCs")
    return _ProbePcs(
        parser_idle_pc=parser_idle_pc & 0xFFFF,
        hid_dispatch_entry_pc=hid_dispatch_entry_pc & 0xFFFF,
        hid_dispatch_return_pc=hid_dispatch_return_pc & 0xFFFF,
    )


def _did_hit_break(cli_text: str, addr: int) -> bool:
    wanted = addr & 0xFFFF
    for match in _EXEC_BREAK_RE.finditer(cli_text):
        if int(match.group(1), 16) == wanted:
            return True
    return False


def _break_hit_count(cli_text: str, addr: int) -> int:
    wanted = addr & 0xFFFF
    hits = 0
    for match in _EXEC_BREAK_RE.finditer(cli_text):
        if int(match.group(1), 16) == wanted:
            hits += 1
    return hits


def _read_regfile(cli_text: str, addr: int) -> int:
    wanted_addr = addr & 0xFF
    for match in _REGFILE_RE.finditer(cli_text):
        if int(match.group(1), 16) != wanted_addr:
            continue
        return int(match.group(2), 16) & 0xFF
    raise AssertionError(f"missing regfile readback for reg{wanted_addr:02x}")


def _read_sfr(cli_text: str, addr: int) -> int:
    wanted_addr = addr & 0xFFFF
    for match in _SFR_RE.finditer(cli_text):
        if int(match.group(1), 16) != wanted_addr:
            continue
        return int(match.group(2), 16) & 0xFF
    raise AssertionError(f"missing MCU register readback for 0x{wanted_addr:03X}")


def _read_sfr_last(cli_text: str, addr: int) -> int:
    wanted_addr = addr & 0xFFFF
    last: int | None = None
    for match in _SFR_RE.finditer(cli_text):
        if int(match.group(1), 16) != wanted_addr:
            continue
        last = int(match.group(2), 16) & 0xFF
    if last is None:
        raise AssertionError(f"missing MCU register readback for 0x{wanted_addr:03X}")
    return last


def _combined_table_bytes() -> bytes:
    mem = parse_intel_hex(STOCK_MAIN_COMBINED_HEX)
    return bytes(mem.get(addr, 0xFF) for addr in range(0x5600, 0x6000))


def _fixture_flash_offsets() -> dict[int, int]:
    table = _combined_table_bytes()
    out: dict[int, int] = {}
    for offset in range(0, len(table) - 23, 24):
        entry = table[offset : offset + 24]
        word0 = entry[0] | (entry[1] << 8)
        word1 = entry[2] | (entry[3] << 8)
        op = word0 & 0xFF
        subaddr = (word0 >> 8) & 0xFF
        payload = entry[4 : 4 + min(word1, 20)]
        if op == 0x01 and any(payload) and subaddr not in out:
            out[subaddr] = 0x5600 + offset
    return out


def _zeroed_entry_seed_hex(output_hex: Path, *, subaddr: int) -> Path:
    mem = dict(parse_intel_hex(STOCK_MAIN_COMBINED_HEX))
    offsets = _fixture_flash_offsets()
    flash_addr = offsets[subaddr]
    payload = dict(_RECOVERED_ENTRY_FIXTURES)[subaddr]
    for addr in range(flash_addr + 4, flash_addr + 4 + len(payload)):
        mem[addr] = 0x00
    write_intel_hex(output_hex, mem)
    return output_hex


def _recovered_first_page_chunk_payloads() -> tuple[bytes, bytes]:
    table = _combined_table_bytes()
    page0 = table[:0xC0]
    return (
        page0[0x00 + 4 : 0x00 + 24],
        page0[0x18 + 4 : 0x18 + 24],
    )


def _resolve_entry_apply_pcs(main_hex: Path) -> tuple[int, int, int]:
    if main_hex == V31_MAIN_HEX:
        lst_path = main_hex.with_suffix(".lst")
        if not lst_path.exists():
            raise AssertionError(f"missing gpasm listing for {main_hex.name}: {lst_path}")
        symbols = parse_gpasm_symbols(lst_path)
        entry_apply_pc = symbols["main_i2c_service_381c"] & 0xFFFF
        buffer_loop_pc = symbols["flow_main_i2c_service_381c_3870"] & 0xFFFF
        return_pc = symbols["flow_main_i2c_service_381c_38a0"] & 0xFFFF
        return _EntryApplyPcs(
            entry_apply_pc=entry_apply_pc,
            # Stop immediately after START is asserted and before the SEN poll loop.
            entry_buffer_ready_pc=(buffer_loop_pc - 2) & 0xFFFF,
            entry_apply_return_pc=return_pc,
        )
    entry_apply_pc = find_code_signature(main_hex, _ENTRY_APPLY_SIG)
    entry_buffer_ready_pc = find_code_signature(main_hex, _ENTRY_BUFFER_READY_SIG)
    entry_return_window_pc = find_code_signature(main_hex, _ENTRY_RETURN_WINDOW_SIG)
    if (
        entry_apply_pc is None
        or entry_buffer_ready_pc is None
        or entry_return_window_pc is None
    ):
        raise AssertionError(f"{main_hex.name}: failed to resolve stock-equivalent entry-apply PCs")
    return _EntryApplyPcs(
        entry_apply_pc=entry_apply_pc & 0xFFFF,
        entry_buffer_ready_pc=entry_buffer_ready_pc & 0xFFFF,
        entry_apply_return_pc=(entry_return_window_pc + 6) & 0xFFFF,
    )


def _run_entry_apply_probe(main_hex: Path, *, flash_addr: int, subaddr: int, length: int) -> str:
    probe_pcs = _resolve_probe_pcs(main_hex)
    entry_pcs = _resolve_entry_apply_pcs(main_hex)

    with tempfile.TemporaryDirectory(prefix="main_combined_table_apply_") as td:
        tdp = Path(td)
        seeded_hex = tdp / "main_seeded.hex"
        sim_hex = tdp / "main_sim.hex"
        boot_stc = tdp / "main_an0_bootstrap.stc"
        i2c_stc = tdp / "main_i2c_bus.stc"
        run_stc = tdp / "main_apply_probe.stc"

        build_seeded_main_sim_hex(main_hex, seeded_hex)
        apply_overlays(seeded_hex, sim_hex, manifests=[main_reset_to_appstart()])
        write_main_an0_bootstrap_stc(boot_stc, processor=MAIN_GPSIM_PROCESSOR)
        write_main_i2c_regfile_stc(
            i2c_stc,
            devices=[MainI2CRegFileDevice("dsp34", 0x34)],
            processor=MAIN_GPSIM_PROCESSOR,
        )

        reg_reads = [
            f"dsp34.reg{(subaddr + offset) & 0xFF:02x}"
            for offset in range(length)
        ]

        stc_lines = [
            f"processor {MAIN_GPSIM_PROCESSOR}",
            f"load {sim_hex}",
            "frequency 16000000",
            f"load {boot_stc}",
            f"load {i2c_stc}",
            f"break e 0x{probe_pcs.parser_idle_pc:04X}",
            "run",
            "clear 0",
            f"reg(0x013)=0x{flash_addr & 0xFF:02X}",
            f"reg(0x014)=0x{(flash_addr >> 8) & 0xFF:02X}",
            f"break e 0x{entry_pcs.entry_apply_return_pc:04X}",
            f"pc=0x{entry_pcs.entry_apply_pc:04X}",
            "run",
            *reg_reads,
            "quit",
            "",
        ]
        run_stc.write_text("\n".join(stc_lines), encoding="ascii")
        cp = subprocess.run(
            [require_gpsim_binary(), "-i", "-c", str(run_stc)],
            text=True,
            capture_output=True,
            check=False,
            timeout=240.0,
        )
        cli_text = cp.stdout + cp.stderr
        if cp.returncode != 0:
            raise RuntimeError(f"gpsim probe failed ({cp.returncode}):\n{cli_text}")
        if not _did_hit_break(cli_text, probe_pcs.parser_idle_pc):
            raise RuntimeError(f"gpsim probe never reached parser loop:\n{cli_text}")
        if not _did_hit_break(cli_text, entry_pcs.entry_apply_return_pc):
            raise RuntimeError(
                f"entry-apply helper did not return at 0x{entry_pcs.entry_apply_return_pc:04X}; "
                f"flash 0x{flash_addr:04X} / subaddr 0x{subaddr:02X} likely stalled "
                f"or crashed.\n{cli_text}"
            )
        return cli_text


def _run_hid_upload_buffer_probe(main_hex: Path, *, cmd: int) -> _UploadBufferProbeResult:
    probe_pcs = _resolve_probe_pcs(main_hex)
    chunk0, chunk1 = _recovered_first_page_chunk_payloads()

    with tempfile.TemporaryDirectory(prefix="main_combined_table_upload_") as td:
        tdp = Path(td)
        custom_seed_hex = tdp / "main_custom_seed.hex"
        seeded_hex = tdp / "main_seeded.hex"
        sim_hex = tdp / "main_sim.hex"
        boot_stc = tdp / "main_an0_bootstrap.stc"
        i2c_stc = tdp / "main_i2c_bus.stc"
        run_stc = tdp / "main_upload_probe.stc"

        _zeroed_entry_seed_hex(custom_seed_hex, subaddr=0x37)
        build_seeded_main_sim_hex(main_hex, seeded_hex, seed_hex=custom_seed_hex)
        apply_overlays(seeded_hex, sim_hex, manifests=[main_reset_to_appstart()])
        write_main_an0_bootstrap_stc(boot_stc, processor=MAIN_GPSIM_PROCESSOR)
        write_main_i2c_regfile_stc(
            i2c_stc,
            devices=[MainI2CRegFileDevice("dsp34", 0x34)],
            processor=MAIN_GPSIM_PROCESSOR,
        )

        stc_lines = [
            f"processor {MAIN_GPSIM_PROCESSOR}",
            f"load {sim_hex}",
            "frequency 16000000",
            f"load {boot_stc}",
            f"load {i2c_stc}",
            f"break e 0x{probe_pcs.parser_idle_pc:04X}",
            "run",
            "clear 0",
        ]
        for chunk_idx, payload in enumerate((chunk0, chunk1)):
            stc_lines.extend(
                [
                    f"reg(0xFE8)=0x{cmd & 0xFF:02X}",
                    f"reg(0x11B)=0x{chunk_idx:02X}",
                    "reg(0x11C)=0x00",
                    "reg(0x11D)=0x00",
                ]
            )
            stc_lines.extend(
                f"reg(0x{0x11E + offset:03X})=0x{value:02X}"
                for offset, value in enumerate(payload)
            )
            stc_lines.extend(
                [
                    f"break e 0x{probe_pcs.hid_dispatch_return_pc:04X}",
                    f"pc=0x{probe_pcs.hid_dispatch_entry_pc:04X}",
                    "run",
                    f"clear {chunk_idx + 1}",
                ]
            )

        for addr in range(0x314, 0x336):
            stc_lines.append(f"reg(0x{addr:03X})")
        stc_lines.extend(
            [
                "reg(0x082)",
                "reg(0x083)",
                "reg(0x0C5)",
                "quit",
                "",
            ]
        )
        run_stc.write_text("\n".join(stc_lines), encoding="ascii")
        cp = subprocess.run(
            [require_gpsim_binary(), "-i", "-c", str(run_stc)],
            text=True,
            capture_output=True,
            check=False,
            timeout=240.0,
        )
        cli_text = cp.stdout + cp.stderr
        if cp.returncode != 0:
            raise RuntimeError(f"gpsim HID upload probe failed ({cp.returncode}):\n{cli_text}")
        if not _did_hit_break(cli_text, probe_pcs.parser_idle_pc):
            raise RuntimeError(f"gpsim HID upload probe never reached parser loop:\n{cli_text}")
        if _break_hit_count(cli_text, probe_pcs.hid_dispatch_return_pc) < 2:
            raise RuntimeError(
                "gpsim HID upload probe did not return from hid_command_dispatch twice.\n"
                f"{cli_text}"
            )

        return _UploadBufferProbeResult(
            page_buffer_window=bytes(_read_sfr(cli_text, addr) for addr in range(0x314, 0x336)),
            flash_page_base=_read_sfr(cli_text, 0x082) | (_read_sfr(cli_text, 0x083) << 8),
            page_chunk_offset=_read_sfr(cli_text, 0x0C5),
        )


def _run_hid_upload_reset_probe(
    main_hex: Path,
    *,
    first_byte: int,
    stale_chunk_offset: int = _STALE_UPLOAD_CHUNK_OFFSET,
    stale_page_base: int = _STALE_UPLOAD_PAGE_BASE,
) -> _UploadBufferProbeResult:
    probe_pcs = _resolve_probe_pcs(main_hex)
    chunk0, _chunk1 = _recovered_first_page_chunk_payloads()

    with tempfile.TemporaryDirectory(prefix="main_combined_table_upload_reset_") as td:
        tdp = Path(td)
        seeded_hex = tdp / "main_seeded.hex"
        sim_hex = tdp / "main_sim.hex"
        boot_stc = tdp / "main_an0_bootstrap.stc"
        i2c_stc = tdp / "main_i2c_bus.stc"
        run_stc = tdp / "main_upload_reset_probe.stc"

        build_seeded_main_sim_hex(main_hex, seeded_hex)
        apply_overlays(seeded_hex, sim_hex, manifests=[main_reset_to_appstart()])
        write_main_an0_bootstrap_stc(boot_stc, processor=MAIN_GPSIM_PROCESSOR)
        write_main_i2c_regfile_stc(
            i2c_stc,
            devices=[MainI2CRegFileDevice("dsp34", 0x34)],
            processor=MAIN_GPSIM_PROCESSOR,
        )

        stc_lines = [
            f"processor {MAIN_GPSIM_PROCESSOR}",
            f"load {sim_hex}",
            "frequency 16000000",
            f"load {boot_stc}",
            f"load {i2c_stc}",
            f"break e 0x{probe_pcs.parser_idle_pc:04X}",
            "run",
            "clear 0",
            "reg(0xFE8)=0x07",
            f"reg(0x0C5)=0x{stale_chunk_offset & 0xFF:02X}",
            f"reg(0x082)=0x{stale_page_base & 0xFF:02X}",
            f"reg(0x083)=0x{(stale_page_base >> 8) & 0xFF:02X}",
            f"reg(0x11B)=0x{first_byte & 0xFF:02X}",
            "reg(0x11C)=0x00",
            "reg(0x11D)=0x00",
        ]
        stc_lines.extend(
            f"reg(0x{0x11E + offset:03X})=0x{value:02X}"
            for offset, value in enumerate(chunk0)
        )
        stc_lines.extend(
            [
                f"break e 0x{probe_pcs.hid_dispatch_return_pc:04X}",
                f"pc=0x{probe_pcs.hid_dispatch_entry_pc:04X}",
                "run",
                "reg(0x082)",
                "reg(0x083)",
                "reg(0x0C5)",
                "quit",
                "",
            ]
        )
        run_stc.write_text("\n".join(stc_lines), encoding="ascii")
        cp = subprocess.run(
            [require_gpsim_binary(), "-i", "-c", str(run_stc)],
            text=True,
            capture_output=True,
            check=False,
            timeout=240.0,
        )
        cli_text = cp.stdout + cp.stderr
        if cp.returncode != 0:
            raise RuntimeError(
                f"gpsim HID upload reset probe failed ({cp.returncode}):\n{cli_text}"
            )
        if not _did_hit_break(cli_text, probe_pcs.parser_idle_pc):
            raise RuntimeError(
                f"gpsim HID upload reset probe never reached parser loop:\n{cli_text}"
            )
        if not _did_hit_break(cli_text, probe_pcs.hid_dispatch_return_pc):
            raise RuntimeError(
                "gpsim HID upload reset probe did not return from hid_command_dispatch.\n"
                f"{cli_text}"
            )

        return _UploadBufferProbeResult(
            page_buffer_window=b"",
            flash_page_base=_read_sfr_last(cli_text, 0x082) | (_read_sfr_last(cli_text, 0x083) << 8),
            page_chunk_offset=_read_sfr_last(cli_text, 0x0C5),
        )


def _run_entry_buffer_probe(main_hex: Path, *, flash_addr: int, length: int) -> str:
    probe_pcs = _resolve_probe_pcs(main_hex)
    entry_pcs = _resolve_entry_apply_pcs(main_hex)

    with tempfile.TemporaryDirectory(prefix="main_combined_table_buffer_") as td:
        tdp = Path(td)
        seeded_hex = tdp / "main_seeded.hex"
        sim_hex = tdp / "main_sim.hex"
        boot_stc = tdp / "main_an0_bootstrap.stc"
        i2c_stc = tdp / "main_i2c_bus.stc"
        run_stc = tdp / "main_buffer_probe.stc"

        build_seeded_main_sim_hex(main_hex, seeded_hex)
        apply_overlays(seeded_hex, sim_hex, manifests=[main_reset_to_appstart()])
        write_main_an0_bootstrap_stc(boot_stc, processor=MAIN_GPSIM_PROCESSOR)
        write_main_i2c_regfile_stc(
            i2c_stc,
            devices=[MainI2CRegFileDevice("dsp34", 0x34)],
            processor=MAIN_GPSIM_PROCESSOR,
        )

        ram_reads = [f"reg(0x{0x017 + offset:03X})" for offset in range(length)]
        stc_lines = [
            f"processor {MAIN_GPSIM_PROCESSOR}",
            f"load {sim_hex}",
            "frequency 16000000",
            f"load {boot_stc}",
            f"load {i2c_stc}",
            f"break e 0x{probe_pcs.parser_idle_pc:04X}",
            "run",
            "clear 0",
            f"reg(0x013)=0x{flash_addr & 0xFF:02X}",
            f"reg(0x014)=0x{(flash_addr >> 8) & 0xFF:02X}",
            f"break e 0x{entry_pcs.entry_buffer_ready_pc:04X}",
            f"pc=0x{entry_pcs.entry_apply_pc:04X}",
            "run",
            *ram_reads,
            "quit",
            "",
        ]
        run_stc.write_text("\n".join(stc_lines), encoding="ascii")
        cp = subprocess.run(
            [require_gpsim_binary(), "-i", "-c", str(run_stc)],
            text=True,
            capture_output=True,
            check=False,
            timeout=240.0,
        )
        cli_text = cp.stdout + cp.stderr
        if cp.returncode != 0:
            raise RuntimeError(f"gpsim buffer probe failed ({cp.returncode}):\n{cli_text}")
        if not _did_hit_break(cli_text, probe_pcs.parser_idle_pc):
            raise RuntimeError(f"gpsim buffer probe never reached parser loop:\n{cli_text}")
        if not _did_hit_break(cli_text, entry_pcs.entry_buffer_ready_pc):
            raise RuntimeError(
                f"entry buffer probe did not stop at 0x{entry_pcs.entry_buffer_ready_pc:04X}.\n{cli_text}"
            )
        return cli_text


def test_recovered_combined_fixtures_match_seed() -> None:
    """Fixture bytes must remain aligned to the recovered combined seed."""
    table = _combined_table_bytes()
    offsets = _fixture_flash_offsets()

    assert len(offsets) >= 91, "recovered combined seed lost non-zero table entries"
    for subaddr, payload in _RECOVERED_ENTRY_FIXTURES:
        flash_addr = offsets.get(subaddr)
        assert flash_addr is not None, f"missing recovered entry for subaddr 0x{subaddr:02X}"
        offset = flash_addr - 0x5600
        entry = table[offset : offset + 24]
        assert entry[0] == 0x01 and entry[1] == subaddr
        assert entry[2] == len(payload) and entry[3] == 0x00
        assert entry[4 : 4 + len(payload)] == payload, (
            f"fixture mismatch for subaddr 0x{subaddr:02X} at 0x{flash_addr:04X}"
        )


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("main_hex", _FIRMWARE_CASES)
@pytest.mark.parametrize("subaddr, payload", _RECOVERED_ENTRY_FIXTURES)
def test_recovered_combined_entry_applies_verbatim(
    main_hex: Path,
    subaddr: int,
    payload: bytes,
) -> None:
    """Recovered non-stock table entries must reach dsp34 byte-for-byte."""
    _require_gpsim()

    flash_addr = _fixture_flash_offsets()[subaddr]
    cli_text = _run_entry_apply_probe(
        main_hex,
        flash_addr=flash_addr,
        subaddr=subaddr,
        length=len(payload),
    )

    mismatches: list[str] = []
    for offset, want in enumerate(payload):
        reg = (subaddr + offset) & 0xFF
        got = _read_regfile(cli_text, reg)
        if got != want:
            mismatches.append(
                f"reg 0x{reg:02X}: expected 0x{want:02X}, got 0x{got:02X}"
            )

    assert not mismatches, (
        f"{main_hex.name}: recovered combined entry 0x{subaddr:02X} from flash "
        f"0x{flash_addr:04X} did not reach dsp34 verbatim. "
        f"First mismatches: {mismatches[:12]}"
    )


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("main_hex", (
    pytest.param(PATCHED_MAIN_HEX_V27, id="v27"),
    pytest.param(V31_MAIN_HEX, id="v31"),
))
def test_entry_0x37_flash_read_buffer_matches_recovered_payload(main_hex: Path) -> None:
    """Distinguish flash_read corruption from later I2C transmit corruption."""
    _require_gpsim()

    subaddr = 0x37
    payload = dict(_RECOVERED_ENTRY_FIXTURES)[subaddr]
    flash_addr = _fixture_flash_offsets()[subaddr]
    cli_text = _run_entry_buffer_probe(
        main_hex,
        flash_addr=flash_addr,
        length=len(payload),
    )

    mismatches: list[str] = []
    for offset, want in enumerate(payload):
        got = _read_sfr(cli_text, 0x017 + offset)
        if got != want:
            mismatches.append(
                f"ram 0x{0x017 + offset:03X}: expected 0x{want:02X}, got 0x{got:02X}"
            )

    assert not mismatches, (
        f"{main_hex.name}: flash_read buffer for recovered entry 0x37 is wrong "
        f"before START. First mismatches: {mismatches[:12]}"
    )


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("cmd, expected_window, expected_page_base", _UPLOAD_CMD_CASES)
@pytest.mark.parametrize("main_hex", _UPLOAD_BUFFER_CASES)
def test_upload_command_family_matches_stock_buffer_shape(
    main_hex: Path,
    cmd: int,
    expected_window: bytes,
    expected_page_base: int,
) -> None:
    """Stock/V2.7/V3.1 must keep the stock baseline per upload opcode."""
    _require_gpsim()

    result = _run_hid_upload_buffer_probe(main_hex, cmd=cmd)
    assert result.page_buffer_window == expected_window, (
        f"{main_hex.name}: cmd 0x{cmd:02X} upload buffer window diverged from "
        "the recovered stock baseline"
    )
    assert result.flash_page_base == expected_page_base, (
        f"{main_hex.name}: cmd 0x{cmd:02X} page base 0x{result.flash_page_base:04X} "
        f"!= 0x{expected_page_base:04X}"
    )
    assert result.page_chunk_offset == 0x30, (
        f"{main_hex.name}: cmd 0x{cmd:02X} chunk offset "
        f"0x{result.page_chunk_offset:02X} != 0x30"
    )


@pytest.mark.gpsim
@pytest.mark.slow
def test_v31_cmd07_preserves_stock_guarded_reseed_behavior() -> None:
    """V3.1 cmd 0x07 must match stock reseed semantics for byte 1."""
    _require_gpsim()

    expected_nonzero_offset = (_STALE_UPLOAD_CHUNK_OFFSET + 0x18) & 0xFF

    stock_nonzero = _run_hid_upload_reset_probe(STOCK_MAIN_HEX, first_byte=0x01)
    assert stock_nonzero.flash_page_base == _STALE_UPLOAD_PAGE_BASE
    assert stock_nonzero.page_chunk_offset == expected_nonzero_offset

    v31_nonzero = _run_hid_upload_reset_probe(V31_MAIN_HEX, first_byte=0x01)
    assert v31_nonzero.flash_page_base == stock_nonzero.flash_page_base, (
        f"{V31_MAIN_HEX.name}: cmd 0x07 nonzero-first-byte page base "
        f"0x{v31_nonzero.flash_page_base:04X} != stock 0x{stock_nonzero.flash_page_base:04X}"
    )
    assert v31_nonzero.page_chunk_offset == stock_nonzero.page_chunk_offset, (
        f"{V31_MAIN_HEX.name}: cmd 0x07 nonzero-first-byte chunk cursor "
        f"0x{v31_nonzero.page_chunk_offset:02X} != stock 0x{stock_nonzero.page_chunk_offset:02X}"
    )

    stock_zero = _run_hid_upload_reset_probe(STOCK_MAIN_HEX, first_byte=0x00)
    assert stock_zero.flash_page_base == 0x5600
    assert stock_zero.page_chunk_offset == 0x18

    v31_zero = _run_hid_upload_reset_probe(V31_MAIN_HEX, first_byte=0x00)
    assert v31_zero.flash_page_base == stock_zero.flash_page_base, (
        f"{V31_MAIN_HEX.name}: cmd 0x07 zero-first-byte page base "
        f"0x{v31_zero.flash_page_base:04X} != stock 0x{stock_zero.flash_page_base:04X}"
    )
    assert v31_zero.page_chunk_offset == stock_zero.page_chunk_offset, (
        f"{V31_MAIN_HEX.name}: cmd 0x07 zero-first-byte chunk cursor "
        f"0x{v31_zero.page_chunk_offset:02X} != stock 0x{stock_zero.page_chunk_offset:02X}"
    )
