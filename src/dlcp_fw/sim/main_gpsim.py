"""Instruction-level main firmware simulation with mailbox RX/TX probes."""

from __future__ import annotations

import re
import subprocess
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence

from dlcp_fw.paths import STOCK_MAIN_COMBINED_HEX

from .gpsim import require_gpsim_binary
from .hexio import parse_intel_hex, write_intel_hex
from .manifests import main_reset_to_appstart, main_serial_mailbox_hooks
from .overlay import apply_overlays
from .paths import MAIN_HEX_PATCHED, SIM_ARTIFACTS_DIR
from .protocol import SerialFrame

MAIN_FAULT_FLAGS_ADDR = 0x7C7
MAIN_NATIVE_TIMEOUT_UART_SEED_ADDR = 0x04E
MAIN_NATIVE_TIMEOUT_MSSP_SEED_ADDR = 0x04F
MAIN_NATIVE_TIMEOUT_SEED_OK = 0x10
MAIN_NATIVE_TIMEOUT_SEED_TIMEOUT = 0x00
MAIN_FAULT_UART_TX_STALL = 0x01
MAIN_FAULT_MSSP_WAIT_STALL = 0x02
MAIN_GPSIM_PROCESSOR = "p18f2455"
MAIN_UART_TRMT_BUSY_CYCLES_ATTR = "usart_trmt_busy_cycles"
MAIN_UART_TRMT_BUSY_COUNT_ATTR = "usart_trmt_busy_count"
MAIN_MSSP_STOP_BUSY_CYCLES_ATTR = "ssp_stop_busy_cycles"
MAIN_MSSP_STOP_BUSY_COUNT_ATTR = "ssp_stop_busy_count"
MAIN_MAILBOX_TX_BASE = 0x740
MAIN_MAILBOX_TX_SIZE = 0x40
MAIN_ADC_VREF_VOLTS = 5.0
MAIN_AN0_BOOT_ADC = 0x0237
MAIN_AN0_BOOT_EXIT_ADDR = 0x2DC8
MAIN_APP_PATCH_START = 0x1000
MAIN_APP_PATCH_LIMIT = 0x5600
_MAIN_EXEC_BREAK_RE = re.compile(r"Execution at .*?\(0x([0-9A-Fa-f]+)\)")
_MAIN_CYCLE_LINE_RE = re.compile(r"^\s*0x([0-9A-Fa-f]+)\s+p18f[0-9A-Za-z]+", re.MULTILINE)
_MAIN_AN0_BOOT_CYCLE_CACHE: dict[str, int] = {}


@dataclass(frozen=True)
class MainI2CRegFileDevice:
    name: str
    slave_address: int
    registers: Mapping[int, int] | None = None
    address_nack_count: int = 0
    address_stretch_scl_cycles: int = 0
    address_stretch_count: int = -1
    data_nack_count: int = 0
    data_stuck_sda_cycles: int = 0
    data_stuck_sda_count: int = -1
    hold_scl_low: bool = False
    stretch_scl_cycles: int = 0


DEFAULT_MAIN_I2C_REGFILE_DEVICES: tuple[MainI2CRegFileDevice, ...] = (
    MainI2CRegFileDevice("cfg71", 0x71),
    MainI2CRegFileDevice("dsp34", 0x34),
)


def default_main_i2c_regfile_devices() -> list[MainI2CRegFileDevice]:
    return [
        MainI2CRegFileDevice(
            device.name,
            device.slave_address,
            None if device.registers is None else dict(device.registers),
            int(device.address_nack_count),
            int(device.address_stretch_scl_cycles),
            int(device.address_stretch_count),
            int(device.data_nack_count),
            int(device.data_stuck_sda_cycles),
            int(device.data_stuck_sda_count),
            bool(device.hold_scl_low),
            int(device.stretch_scl_cycles),
        )
        for device in DEFAULT_MAIN_I2C_REGFILE_DEVICES
    ]


def _clamp_main_adc(adc: int) -> int:
    return max(0, min(0x03FF, int(adc)))


def main_adc_to_voltage(adc: int, *, vref_volts: float = MAIN_ADC_VREF_VOLTS) -> float:
    return (_clamp_main_adc(adc) / 1023.0) * vref_volts


def write_main_an0_bootstrap_stc(
    path: Path,
    *,
    adc: int = MAIN_AN0_BOOT_ADC,
    post_boot_adc: int | None = None,
    post_boot_cycle: int | None = None,
    processor: str = MAIN_GPSIM_PROCESSOR,
    name_prefix: str = "an0_boot",
) -> None:
    voltage = main_adc_to_voltage(adc)
    data_points = [f"100, {voltage:.6f}"]
    if post_boot_adc is not None and post_boot_cycle is not None:
        post_voltage = main_adc_to_voltage(post_boot_adc)
        data_points.append(f"{int(post_boot_cycle)}, {post_voltage:.6f}")
    node_name = f"{name_prefix}_node"
    stim_name = f"{name_prefix}_stim"
    path.write_text(
        textwrap.dedent(
            f"""\
            module library libgpsim_modules
            node {node_name}
            stimulus asynchronous_stimulus
            initial_state {voltage:.6f}
            start_cycle 1
            period 10000000
            analog
            {{ {", ".join(data_points)} }}
            name {stim_name}
            end
            attach {node_name} {stim_name} {processor}.porta0
            """
        ),
        encoding="ascii",
    )


def write_main_i2c_regfile_stc(
    path: Path,
    *,
    devices: Sequence[MainI2CRegFileDevice],
    processor: str = MAIN_GPSIM_PROCESSOR,
    sda_node: str = "main_i2c_sda",
    scl_node: str = "main_i2c_scl",
) -> None:
    lines = [
        "module library libgpsim_modules",
        "module load pullup main_i2c_sda_pullup",
        "module load pullup main_i2c_scl_pullup",
    ]
    for device in devices:
        lines.append(f"module load i2c_regfile {device.name}")
        lines.append(f"{device.name}.Slave_Address = {int(device.slave_address) & 0x7F}")
        if int(device.address_nack_count) != 0:
            lines.append(f"{device.name}.Address_Nack_Count = {int(device.address_nack_count)}")
        if int(device.address_stretch_scl_cycles) > 0:
            lines.append(
                f"{device.name}.Address_Stretch_SCL_Cycles = {int(device.address_stretch_scl_cycles)}"
            )
            if int(device.address_stretch_count) >= 0:
                lines.append(f"{device.name}.Address_Stretch_Count = {int(device.address_stretch_count)}")
        if int(device.data_nack_count) != 0:
            lines.append(f"{device.name}.Data_Nack_Count = {int(device.data_nack_count)}")
        if int(device.data_stuck_sda_cycles) > 0:
            lines.append(f"{device.name}.Data_Stuck_SDA_Cycles = {int(device.data_stuck_sda_cycles)}")
            if int(device.data_stuck_sda_count) >= 0:
                lines.append(f"{device.name}.Data_Stuck_SDA_Count = {int(device.data_stuck_sda_count)}")
        if bool(device.hold_scl_low):
            lines.append(f"{device.name}.Hold_SCL_Low = 1")
        if int(device.stretch_scl_cycles) > 0:
            lines.append(f"{device.name}.Stretch_SCL_Cycles = {int(device.stretch_scl_cycles)}")
        for addr, value in sorted((device.registers or {}).items()):
            lines.append(f"{device.name}.reg{addr & 0xFF:02x} = ${value & 0xFF:02x}")

    sda_attach = [f"{processor}.portb0", "main_i2c_sda_pullup.pin"]
    scl_attach = [f"{processor}.portb1", "main_i2c_scl_pullup.pin"]
    for device in devices:
        sda_attach.append(f"{device.name}.SDA")
        scl_attach.append(f"{device.name}.SCL")

    lines.extend(
        [
            f"node {sda_node}",
            f"attach {sda_node} {' '.join(sda_attach)}",
            f"node {scl_node}",
            f"attach {scl_node} {' '.join(scl_attach)}",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="ascii")


def _parse_main_exec_break(cli_text: str) -> int | None:
    match = _MAIN_EXEC_BREAK_RE.search(cli_text)
    if match is None:
        return None
    return int(match.group(1), 16) & 0xFFFF


def _parse_main_cycle(cli_text: str) -> int:
    match = _MAIN_CYCLE_LINE_RE.search(cli_text)
    if match is None:
        raise RuntimeError("unable to parse cycle counter from gpsim output")
    return int(match.group(1), 16)


def build_seeded_main_sim_hex(
    main_hex: Path,
    output_hex: Path,
    *,
    seed_hex: Path = STOCK_MAIN_COMBINED_HEX,
) -> Path:
    """
    Materialize a full-device MAIN image for gpsim from an app-only input HEX.

    The stock/patched MAIN release HEX files are application-only images.  For
    gpsim we want recovered-device context by default, so app-only inputs are
    merged onto the dump-based V2.3 combined seed:
    - preserve boot block, config bytes, EEPROM, and User ID from the seed
    - preserve recovered preset/DSP table space at 0x5600..0x5FFF
    - replace app code/data at 0x1000..0x55FF from the input HEX

    If the input HEX already carries a programmed boot block, it is treated as
    a full-device image and copied verbatim.
    """

    source_hex = Path(main_hex)
    seed_source = Path(seed_hex)
    source_mem = parse_intel_hex(source_hex)
    has_boot_block = any(
        0x0000 <= addr < MAIN_APP_PATCH_START and value != 0xFF
        for addr, value in source_mem.items()
    )

    output_hex.parent.mkdir(parents=True, exist_ok=True)
    if has_boot_block:
        output_hex.write_bytes(source_hex.read_bytes())
        return output_hex

    merged = dict(parse_intel_hex(seed_source))
    for addr, value in source_mem.items():
        if MAIN_APP_PATCH_START <= addr < MAIN_APP_PATCH_LIMIT:
            merged[addr] = value & 0xFF
    write_intel_hex(output_hex, merged)
    return output_hex


def probe_main_an0_boot_exit_cycle(
    main_hex: Path,
    *,
    boot_exit_addr: int = MAIN_AN0_BOOT_EXIT_ADDR,
) -> int:
    cache_key = str(Path(main_hex).resolve())
    cached = _MAIN_AN0_BOOT_CYCLE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    with tempfile.TemporaryDirectory(prefix="main_an0_boot_probe_") as td:
        tdp = Path(td)
        seeded_hex = tdp / "main_seeded.hex"
        sim_hex = tdp / "main_sim.hex"
        boot_stc = tdp / "main_an0_bootstrap.stc"
        probe_stc = tdp / "main_an0_probe.stc"

        build_seeded_main_sim_hex(main_hex, seeded_hex)
        apply_overlays(seeded_hex, sim_hex, manifests=[main_reset_to_appstart()])
        write_main_an0_bootstrap_stc(boot_stc, processor=MAIN_GPSIM_PROCESSOR)
        probe_stc.write_text(
            "\n".join(
                [
                    f"processor {MAIN_GPSIM_PROCESSOR}",
                    f"load {sim_hex}",
                    "frequency 16000000",
                    f"load {boot_stc}",
                    f"break e 0x{boot_exit_addr:04X}",
                    "run",
                    "quit",
                    "",
                ]
            ),
            encoding="ascii",
        )
        cp = subprocess.run(
            [require_gpsim_binary(), "-i", "-c", str(probe_stc)],
            text=True,
            capture_output=True,
            check=False,
        )
        cli_text = cp.stdout + cp.stderr
        if cp.returncode != 0:
            raise RuntimeError(f"gpsim exited {cp.returncode} while probing AN0 boot cycle:\n{cli_text}")
        if _parse_main_exec_break(cli_text) != (boot_exit_addr & 0xFFFF):
            raise RuntimeError(f"gpsim did not reach AN0 boot exit 0x{boot_exit_addr:04X}:\n{cli_text}")
        cycle = _parse_main_cycle(cli_text)
        _MAIN_AN0_BOOT_CYCLE_CACHE[cache_key] = cycle
        return cycle


@dataclass(frozen=True)
class MainGpsimResult:
    sim_hex: Path
    log_path: Path
    cli_path: Path
    tx_bytes: List[int]
    regs: Dict[int, int]
    cycles: int
    parser_break_hit: bool = False


@dataclass(frozen=True)
class MainCmd03DispatchResult:
    sim_hex: Path
    cli_path: Path
    regs: Dict[int, int]
    parser_break_hit: bool
    label003_break_hit: bool
    return_break_hit: bool


def _build_frame_bytes(frames: Sequence[SerialFrame]) -> List[int]:
    out: List[int] = []
    for f in frames:
        n = f.normalized()
        out.extend([n.route, n.cmd, n.data])
    return out


def _build_script(
    sim_hex: Path,
    log_path: Path,
    cycles: int,
    parser_break_addr: int,
    rx_bytes: Sequence[int],
    fault_flags: int,
    cli_path: Path,
    watch_regs: Iterable[int],
) -> str:
    lines = [
        f"processor {MAIN_GPSIM_PROCESSOR}",
        f"load {sim_hex}",
        f"log on {log_path}",
        "log w txreg",
        # Stage 1: run boot/init until parser loop entry (0x1BEA).
        f"break e 0x{parser_break_addr:04X}",
        "run",
        # Stage 2: inject mailbox after RAM init is complete.
        "reg(0x7c0)=0x00",  # rx_rd
        f"reg(0x7c1)=0x{len(rx_bytes) & 0xFF:02X}",  # rx_wr
        "reg(0x7c2)=0x00",  # tx_rd (reserved)
        "reg(0x7c3)=0x00",  # tx_wr
        f"reg(0x{MAIN_FAULT_FLAGS_ADDR:03x})=0x{fault_flags & 0xFF:02X}",
    ]
    for i, b in enumerate(rx_bytes):
        lines.append(f"reg(0x{(0x780 + i):03x})=0x{b & 0xFF:02X}")
    lines.extend(
        [
            "clear 0",
            "clear 1",
            f"break c {cycles}",
            "run",
            "log off",
        ]
    )
    for r in watch_regs:
        lines.append(f"reg(0x{r:03x})")
    lines.append("quit")
    text = "\n".join(lines) + "\n"
    cli_path.with_suffix(".stc").write_text(text, encoding="ascii")
    return text


def _parse_tx_bytes(log_path: Path) -> List[int]:
    # gpsim log style includes lines like:
    # Write: 0xBF to TXREG(0x0FAD)
    # Wrote: 0x00BF to txreg(0x0fad)
    p = re.compile(r"Wr(?:ite|ote):\s+0x([0-9A-Fa-f]+)\s+to TXREG\(0x0FAD\)", re.IGNORECASE)
    out: List[int] = []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = p.search(line)
        if m:
            out.append(int(m.group(1), 16) & 0xFF)
    return out


def _parse_regs(cli_text: str) -> Dict[int, int]:
    # Example:
    # REG05E[0x5e] = 0x04 was 0x00
    p = re.compile(r"REG([0-9A-Fa-f]{3})\[0x([0-9A-Fa-f]+)\]\s*=\s*0x([0-9A-Fa-f]+)")
    out: Dict[int, int] = {}
    for line in cli_text.splitlines():
        m = p.search(line)
        if m:
            addr = int(m.group(2), 16)
            val = int(m.group(3), 16)
            out[addr] = val
    return out


def _mailbox_tx_bytes(regs: Mapping[int, int]) -> List[int]:
    rd = regs.get(0x7C2, 0) & 0xFF
    wr = regs.get(0x7C3, 0) & 0xFF
    out: List[int] = []
    cur = rd
    while cur != wr:
        addr = MAIN_MAILBOX_TX_BASE + (cur & 0x3F)
        out.append(regs.get(addr, 0) & 0xFF)
        cur = (cur + 1) & 0xFF
        if len(out) > MAIN_MAILBOX_TX_SIZE:
            break
    return out


def _did_hit_break(cli_text: str, addr: int) -> bool:
    pat = rf"line_{addr:04x}\(0x{addr:04x}\)"
    return bool(re.search(pat, cli_text, flags=re.IGNORECASE))


def _timeout_text(data: str | bytes | None) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data


def run_main_mailbox_gpsim(
    frames: Sequence[SerialFrame],
    *,
    main_hex: Path = MAIN_HEX_PATCHED,
    gpasm: str = "gpasm",
    cycles: int = 120_000_000,
    parser_break_addr: int = 0x1BEA,
    stage1_timeout_s: float = 20.0,
    keep_artifacts: bool = False,
    artifact_dir: Path | None = None,
    fault_flags: int = 0,
) -> MainGpsimResult:
    rx_bytes = _build_frame_bytes(frames)
    if len(rx_bytes) > 32:
        raise ValueError(f"mailbox supports at most 32 bytes, got {len(rx_bytes)}")
    # Include legacy command side-effect registers used by compatibility tests.
    watch_regs = [
        0x05E,
        0x066,  # volume signed 32-bit cache (low)
        0x067,
        0x068,
        0x069,  # volume signed 32-bit cache (high)
        0x06E,  # latest computed volume signed value (low)
        0x06F,
        0x070,
        0x071,  # latest computed volume signed value (high)
        0x07E,  # dirty flags for DSP updates
        0x07F,  # timeout/display dirty flags
        0x094,  # main state bitfield used in command handlers
        0x099,  # source config shadow
        0x0A1,
        0x0A2,
        0x0A3,
        0x0A5,  # ch1 source
        0x0A6,  # ch2 source
        0x0A7,  # ch3 source / timeout
        0x0A8,  # ch4 source
        0x0A9,  # ch5 source
        0x0AA,  # ch6 source
        0x0B2,  # link address (cmd 0x1E)
        0x0B3,  # source config mirror (cmd 0x06)
        0x0B8,  # display/backlight timeout (cmd 0x1D)
        0x0BC,  # command response byte staging
        0x0C3,  # mirrored link address (cmd 0x1E)
        0x7C0,
        0x7C1,
        0x7C2,
        0x7C3,
        MAIN_FAULT_FLAGS_ADDR,
    ]
    watch_regs.extend(range(MAIN_MAILBOX_TX_BASE, MAIN_MAILBOX_TX_BASE + MAIN_MAILBOX_TX_SIZE))

    with tempfile.TemporaryDirectory(prefix="main_mailbox_sim_") as td:
        tdp = Path(td)
        seeded_hex = tdp / "main_seeded.hex"
        sim_hex = tdp / "main_sim.hex"
        log_path = tdp / "main_gpsim.log"
        cli_path = tdp / "main_gpsim_cli.txt"

        build_seeded_main_sim_hex(main_hex, seeded_hex)
        apply_overlays(
            seeded_hex,
            sim_hex,
            manifests=[main_reset_to_appstart(), main_serial_mailbox_hooks(gpasm=gpasm)],
        )

        stc_path = cli_path.with_suffix(".stc")
        script_text = _build_script(
            sim_hex=sim_hex,
            log_path=log_path,
            cycles=cycles,
            parser_break_addr=parser_break_addr,
            rx_bytes=rx_bytes,
            fault_flags=fault_flags,
            cli_path=cli_path,
            watch_regs=watch_regs,
        )
        gpsim_bin = require_gpsim_binary()
        try:
            cp = subprocess.run(
                [gpsim_bin, "-i", "-c", str(stc_path)],
                text=True,
                capture_output=True,
                check=False,
                timeout=stage1_timeout_s + 20.0,
            )
        except subprocess.TimeoutExpired as exc:
            cli_path.write_text(_timeout_text(exc.stdout) + _timeout_text(exc.stderr), encoding="utf-8")
            raise RuntimeError(f"gpsim timed out after {exc.timeout}s; inspect {cli_path}") from exc
        cli_text = cp.stdout + cp.stderr
        cli_path.write_text(cli_text, encoding="utf-8")
        if cp.returncode != 0:
            raise RuntimeError(f"gpsim exited {cp.returncode}; inspect {cli_path}")
        parser_break_hit = bool(
            re.search(rf"\b0x{parser_break_addr:04x}\b", cli_text, flags=re.IGNORECASE)
        )
        if not parser_break_hit:
            raise RuntimeError(
                f"gpsim did not reach parser break 0x{parser_break_addr:04X}; inspect {cli_path}"
            )
        if "cycle break:" not in cli_text:
            raise RuntimeError(f"gpsim did not hit cycle break; inspect {cli_path}")

        regs = _parse_regs(cli_text)
        tx_bytes = _mailbox_tx_bytes(regs)
        if not tx_bytes:
            tx_bytes = _parse_tx_bytes(log_path)

        if keep_artifacts:
            if artifact_dir is None:
                artifact_dir = SIM_ARTIFACTS_DIR / "main_mailbox_last"
            artifact_dir.mkdir(parents=True, exist_ok=True)
            (artifact_dir / "main_sim.hex").write_bytes(sim_hex.read_bytes())
            (artifact_dir / "main_gpsim.log").write_bytes(log_path.read_bytes())
            (artifact_dir / "main_gpsim_cli.txt").write_text(cli_text, encoding="utf-8")
            (artifact_dir / "main_gpsim.stc").write_text(script_text, encoding="ascii")
            return MainGpsimResult(
                sim_hex=artifact_dir / "main_sim.hex",
                log_path=artifact_dir / "main_gpsim.log",
                cli_path=artifact_dir / "main_gpsim_cli.txt",
                tx_bytes=tx_bytes,
                regs=regs,
                cycles=cycles,
                parser_break_hit=parser_break_hit,
            )

        return MainGpsimResult(
            sim_hex=sim_hex,
            log_path=log_path,
            cli_path=cli_path,
            tx_bytes=tx_bytes,
            regs=regs,
            cycles=cycles,
            parser_break_hit=parser_break_hit,
        )


def run_main_cmd03_dispatch_gpsim(
    *,
    subcmd: int,
    payload: bytes = b"",
    main_hex: Path = MAIN_HEX_PATCHED,
    gpasm: str = "gpasm",
    parser_break_addr: int = 0x1BEA,
    label003_break_addr: int = 0x10D0,
    return_break_addr: int = 0x15AA,
    dispatch_entry_pc: int = 0x3A7E,
    sentinel_regs: Mapping[int, int] | None = None,
    timeout_s: float = 30.0,
    keep_artifacts: bool = False,
    artifact_dir: Path | None = None,
) -> MainCmd03DispatchResult:
    """
    Run a strict instruction-level cmd=0x03 dispatch probe on MAIN firmware.

    The harness boots to parser idle, injects a command window at 0x11A..,
    then jumps to the parser call-site (0x3A7E) and validates execution hits:
    - label_003 (0x10D0): cmd=0x03 handler entry
    - label_083 (0x15AA): command completion/return path
    """
    sub = subcmd & 0xFF
    data = bytes(payload[:30])
    sentinels = {int(k) & 0xFFF: int(v) & 0xFF for k, v in (sentinel_regs or {}).items()}

    watch_regs: List[int] = [
        0x05E,
        0x073,
        0x074,
        0x097,
        0x099,
        0x0A5,
        0x0A6,
        0x0A7,
        0x0A8,
        0x0A9,
        0x0AA,
        0x0B2,
        0x0B3,
        0x0B8,
        0x0BD,
        0x0C0,
        0x11A,
        0x11B,
    ]
    watch_regs.extend(range(0x2C0, 0x2DE))
    watch_regs.extend(sentinels.keys())
    watch_regs = list(dict.fromkeys(watch_regs))

    with tempfile.TemporaryDirectory(prefix="main_cmd03_dispatch_sim_") as td:
        tdp = Path(td)
        seeded_hex = tdp / "main_seeded.hex"
        sim_hex = tdp / "main_cmd03_sim.hex"
        cli_path = tdp / "main_cmd03_gpsim_cli.txt"
        stc_path = cli_path.with_suffix(".stc")

        build_seeded_main_sim_hex(main_hex, seeded_hex)
        apply_overlays(
            seeded_hex,
            sim_hex,
            manifests=[
                main_reset_to_appstart(),
                main_serial_mailbox_hooks(gpasm=gpasm),
            ],
        )

        lines = [
            f"processor {MAIN_GPSIM_PROCESSOR}",
            f"load {sim_hex}",
            f"break e 0x{parser_break_addr:04X}",
            "run",
        ]
        for addr, val in sentinels.items():
            lines.append(f"reg(0x{addr:03x})=0x{val:02X}")

        # Clear payload window to deterministic 0x00 bytes.
        for i in range(30):
            lines.append(f"reg(0x{(0x11C + i):03x})=0x00")
        for i, b in enumerate(data):
            lines.append(f"reg(0x{(0x11C + i):03x})=0x{b:02X}")

        lines.extend(
            [
                "reg(0x11a)=0x03",
                f"reg(0x11b)=0x{sub:02X}",
                "reg(0x0c0)=0x01",
                f"pc=0x{dispatch_entry_pc:04X}",
                f"break e 0x{label003_break_addr:04X}",
                "run",
                f"break e 0x{return_break_addr:04X}",
                "run",
            ]
        )
        for r in watch_regs:
            lines.append(f"reg(0x{r:03x})")
        lines.extend(["quit", ""])
        stc_path.write_text("\n".join(lines), encoding="ascii")
        gpsim_bin = require_gpsim_binary()

        try:
            cp = subprocess.run(
                [gpsim_bin, "-i", "-c", str(stc_path)],
                text=True,
                capture_output=True,
                check=False,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            cli_path.write_text(_timeout_text(exc.stdout) + _timeout_text(exc.stderr), encoding="utf-8")
            raise RuntimeError(f"gpsim cmd03 probe timed out after {exc.timeout}s; inspect {cli_path}") from exc
        cli_text = cp.stdout + cp.stderr
        cli_path.write_text(cli_text, encoding="utf-8")
        if cp.returncode != 0:
            raise RuntimeError(f"gpsim cmd03 probe exited {cp.returncode}; inspect {cli_path}")

        parser_break_hit = _did_hit_break(cli_text, parser_break_addr)
        label003_break_hit = _did_hit_break(cli_text, label003_break_addr)
        return_break_hit = _did_hit_break(cli_text, return_break_addr)
        if not parser_break_hit:
            raise RuntimeError(
                f"gpsim cmd03 probe did not reach parser break 0x{parser_break_addr:04X}; inspect {cli_path}"
            )
        if not label003_break_hit:
            raise RuntimeError(
                f"gpsim cmd03 probe did not hit label_003 at 0x{label003_break_addr:04X}; inspect {cli_path}"
            )
        if not return_break_hit:
            raise RuntimeError(
                f"gpsim cmd03 probe did not hit return break 0x{return_break_addr:04X}; inspect {cli_path}"
            )

        regs = _parse_regs(cli_text)

        if keep_artifacts:
            if artifact_dir is None:
                artifact_dir = SIM_ARTIFACTS_DIR / "main_cmd03_dispatch_last"
            artifact_dir.mkdir(parents=True, exist_ok=True)
            (artifact_dir / "main_cmd03_sim.hex").write_bytes(sim_hex.read_bytes())
            (artifact_dir / "main_cmd03_gpsim_cli.txt").write_text(cli_text, encoding="utf-8")
            (artifact_dir / "main_cmd03_gpsim.stc").write_text("\n".join(lines), encoding="ascii")
            return MainCmd03DispatchResult(
                sim_hex=artifact_dir / "main_cmd03_sim.hex",
                cli_path=artifact_dir / "main_cmd03_gpsim_cli.txt",
                regs=regs,
                parser_break_hit=parser_break_hit,
                label003_break_hit=label003_break_hit,
                return_break_hit=return_break_hit,
            )

        return MainCmd03DispatchResult(
            sim_hex=sim_hex,
            cli_path=cli_path,
            regs=regs,
            parser_break_hit=parser_break_hit,
            label003_break_hit=label003_break_hit,
            return_break_hit=return_break_hit,
        )
