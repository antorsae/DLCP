"""V3.2 SRC4382/input-service regression coverage.

The 2026-05-19 Auto Detect cadence experiment replaced the legacy
``main_i2c_service_27f0`` body and field hardware immediately reported a
thin/no-bass audio regression.  Keep the release on the known-good
stock-equivalent SRC4382/input service until a future redesign proves audio
parity on hardware.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from dlcp_fw.paths import V32_MAIN_ASM
from dlcp_fw.sim.v30_symbols import assemble_v30


ACTIVE_FLAGS = 0x05E
EVENT_FLAGS = 0x07E
SRC_ROUTE_REQUEST = 0x093
INPUT_SELECT = 0x099
INPUT_SELECT_MIRROR = 0x0B3
ROUTE_SHADOW = 0x0AB
SCAN_CANDIDATE_INDEX = 0x0B6
SCAN_MISS_DEBOUNCE = 0x0BA
I2C_SLOW_COUNTER = 0x0BB

SRC_REG_RX_CONTROL = 0x0D
SRC_REG_TX_CONTROL_2 = 0x08
SRC_REG_NON_PCM = 0x12
SRC_REG_RX_STATUS = 0x13
TAS_REG_VOLUME_COEFF = 0x30

BOOT_TCY = 16_000_000
COMMAND_SETTLE_TCY = 8_000_000


@pytest.fixture(scope="module")
def v32_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v32_src4382_audio_path")
    hex_out = tmp / "DLCP_Firmware_V3.2.hex"
    assemble_v30(V32_MAIN_ASM, hex_out)
    return hex_out


def _rust_chain():
    try:
        from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    except Exception as exc:  # pragma: no cover
        pytest.fail(f"rust dlcp_sim_native facade not importable -- {exc!r}")
    return RustChain


def _label_body(text: str, start: str, end: str) -> str:
    pattern = rf"^{re.escape(start)}:\n(?P<body>.*?)(?=^{re.escape(end)}:)"
    match = re.search(pattern, text, flags=re.MULTILINE | re.DOTALL)
    assert match, f"could not find label body {start}..{end}"
    return match.group("body")


def _boot_active_main(v32_hex: Path):  # type: ignore[no-untyped-def]
    chain = _rust_chain().from_v3x_main_only(str(v32_hex))
    chain.step_tcy(BOOT_TCY)
    assert chain.read_reg(ACTIVE_FLAGS) & 0x08, "MAIN did not reach active app state"
    return chain


def _assemble_mutated_v32(tmp_path: Path, text: str) -> Path:
    """Assemble a generated V3.2 mutation beside its include file."""
    shutil.copy2(V32_MAIN_ASM.parent / "dlcp_main_ram.inc", tmp_path / "dlcp_main_ram.inc")
    asm_path = tmp_path / "dlcp_main_v32_mutated.asm"
    hex_path = tmp_path / "DLCP_Firmware_V3.2_mutated.hex"
    asm_path.write_text(text, encoding="utf-8")
    assemble_v30(asm_path, hex_path)
    return hex_path


def _assert_autodetect_source_present_drives_route_and_dsp(v32_hex: Path) -> None:
    """Exercise the real Auto Detect service, not a directly forced route event."""
    chain = _boot_active_main(v32_hex)

    # Force a deterministic source-present scan on candidate 0.  Legacy V3.2
    # maps candidate 0 / RX value 0x08 to DLCP route request 3, which must then
    # pass through cmd_dispatch_gated and refresh TAS3108 coefficient 0x30.
    chain.write_reg(INPUT_SELECT, 0x00)
    chain.write_reg(INPUT_SELECT_MIRROR, 0x00)
    chain.write_reg(ROUTE_SHADOW, 0x00)
    chain.write_reg(SCAN_CANDIDATE_INDEX, 0x00)
    chain.write_reg(SCAN_MISS_DEBOUNCE, 0x00)
    chain.write_reg(I2C_SLOW_COUNTER, 0x65)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x01)
    chain.poke_main_src4382_reg(0, SRC_REG_NON_PCM, 0x00)
    chain.reset_main_src4382_stats(0)
    chain.reset_main_dsp_write_log(0)

    chain.step_tcy(2_000_000)

    assert chain.read_reg(SRC_ROUTE_REQUEST) == 0x03
    assert chain.read_reg(ROUTE_SHADOW) == 0x03
    tx_values = chain.read_main_src4382_write_values(0, SRC_REG_TX_CONTROL_2)
    assert 0x30 in tx_values, (
        "Auto Detect route reconciliation did not write SRC4382 transmitter "
        f"route 0x08=0x30; writes={tx_values!r}"
    )
    volume_payload = chain.read_main_dsp_write_payload(0, TAS_REG_VOLUME_COEFF)
    assert volume_payload is not None, (
        "Auto Detect route reconciliation did not refresh TAS3108 coefficient 0x30"
    )
    assert len(volume_payload) == 4


def test_v32_src4382_service_retains_legacy_dsp_refresh_contract() -> None:
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    body = _label_body(text, "main_i2c_service_27f0", "main_core_service_297e")
    dispatch = _label_body(text, "cmd_dispatch_gated", "cmd_gate_reject")

    assert "src4382_autodetect_service" not in body
    assert "ram_0x0BB" in body, "legacy slow-service loop counter was removed"
    assert "movlw       0x17" not in body, (
        "real hardware rejected the May 2026 Auto Detect dwell throttle; "
        "do not reintroduce it without acoustic proof"
    )
    assert "xorwf       ram_0x0BF" not in body, (
        "ram_0x0BF must remain the legacy 0x12 status scratch, not a "
        "last-written 0x0D shadow"
    )
    assert re.search(
        r"movlw\s+0x0D\s*\n\s*call\s+i2c_secondary_dev_write",
        body,
    ), "legacy SRC4382 receiver-select write to register 0x0D is missing"
    assert re.search(
        r"movlw\s+0x13\s*\n\s*call\s+i2c_secondary_dev_random_read",
        body,
    ), "legacy recovered-clock status read from register 0x13 is missing"
    assert re.search(
        r"movlw\s+0x12\s*\n\s*call\s+i2c_secondary_dev_random_read",
        body,
    ), "legacy non-PCM/status read from register 0x12 is missing"
    assert re.search(
        r"movlw\s+0x12\s*\n"
        r"\s*call\s+i2c_secondary_dev_random_read.*?"
        r"movwf\s+ram_0x0BF, BANKED",
        body,
        flags=re.DOTALL,
    ), "legacy register 0x12 result must be staged in ram_0x0BF"
    assert re.search(
        r"movf\s+ram_0x0AB, W, BANKED.*?"
        r"xorwf\s+ram_0x093, W, BANKED.*?"
        r"bsf\s+event_flags, 1, BANKED.*?"
        r"movff\s+ram_0x093, ram_0x0AB",
        body,
        flags=re.DOTALL,
    ), "legacy route-change event/shadow reconciliation is missing"
    assert "bsf         event_flags, 5" in body
    assert "bsf         active_flags, 4" in body
    assert "bsf         active_flags, 5" in body
    assert "bcf         active_flags, 5" in body
    for rx_control, tx_control_2 in (
        (0x09, 0x70),
        (0x0A, 0xB0),
        (0x08, 0x30),
        (0x0B, 0xF0),
    ):
        assert re.search(
            rf"movlw\s+0x{rx_control:02X}.*?"
            rf"movlw\s+0x{tx_control_2:02X}.*?"
            r"cmd_dispatch_gated_i2c_pair",
            dispatch,
            flags=re.DOTALL,
        ), (
            f"cmd_dispatch_gated route pair 0x{rx_control:02X}/"
            f"0x{tx_control_2:02X} is missing"
        )
    assert re.search(
        r"movlw\s+0x08\s*\n\s*call\s+i2c_secondary_dev_write",
        dispatch,
    ), "SRC4382 route-pair write to register 0x08 is missing"
    assert "call        volume_dsp_write" in dispatch


def test_v32_src4382_legacy_service_polls_status_registers(v32_hex: Path) -> None:
    chain = _boot_active_main(v32_hex)

    chain.write_reg(INPUT_SELECT, 0x00)
    chain.write_reg(INPUT_SELECT_MIRROR, 0x00)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x01)
    chain.poke_main_src4382_reg(0, SRC_REG_NON_PCM, 0x00)
    chain.reset_main_src4382_stats(0)

    chain.step_tcy(4_000_000)

    stats = chain.read_main_src4382_stats(0)
    assert stats["writes_by_subaddr"][SRC_REG_RX_CONTROL] > 0, stats
    assert stats["reads_by_subaddr"][SRC_REG_RX_STATUS] > 0, stats
    assert stats["reads_by_subaddr"][SRC_REG_NON_PCM] > 0, stats


def test_v32_autodetect_source_present_drives_route_event_and_dsp_refresh(
    v32_hex: Path,
) -> None:
    _assert_autodetect_source_present_drives_route_and_dsp(v32_hex)


def test_v32_audio_path_safety_guard_rejects_missing_route_event_mutation(
    tmp_path: Path,
) -> None:
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    old = (
        "    bsf         event_flags, 1, BANKED\n"
        "    movff       ram_0x093, ram_0x0AB"
    )
    assert old in text, "route-event mutation anchor drifted"
    mutated_hex = _assemble_mutated_v32(
        tmp_path,
        text.replace(old, "    nop\n    movff       ram_0x093, ram_0x0AB", 1),
    )

    with pytest.raises(AssertionError, match="did not write SRC4382 transmitter route"):
        _assert_autodetect_source_present_drives_route_and_dsp(mutated_hex)


def test_v32_audio_path_safety_guard_rejects_missing_tas_refresh_mutation(
    tmp_path: Path,
) -> None:
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    old = "i2c_tas3108_coeff_write:\n    rcall       i2c_wait_bus_idle"
    assert old in text, "TAS refresh mutation anchor drifted"
    mutated_hex = _assemble_mutated_v32(
        tmp_path,
        text.replace(old, "i2c_tas3108_coeff_write:\n    return      0\n", 1),
    )

    with pytest.raises(AssertionError, match="did not refresh TAS3108 coefficient"):
        _assert_autodetect_source_present_drives_route_and_dsp(mutated_hex)


@pytest.mark.parametrize(
    ("route_request", "rx_control", "tx_control_2"),
    [
        (0x01, 0x09, 0x70),
        (0x02, 0x0A, 0xB0),
        (0x03, 0x08, 0x30),
        (0x04, 0x0B, 0xF0),
    ],
)
def test_v32_route_event_applies_src_route_and_dsp_refresh(
    v32_hex: Path,
    route_request: int,
    rx_control: int,
    tx_control_2: int,
) -> None:
    """The route event produced by the SRC4382/input service must update
    the SRC4382 audio route and drive the downstream TAS3108 refresh.

    This pins the contract that the failed Auto Detect rewrite missed:
    ``main_i2c_service_27f0`` computes ``ram_0x093`` and sets
    ``event_flags.bit1``; ``cmd_dispatch_gated`` consumes that event by
    writing the SRC route pair and refreshing TAS3108 coefficient 0x30.
    """
    chain = _boot_active_main(v32_hex)
    chain.reset_main_src4382_stats(0)
    chain.reset_main_dsp_write_log(0)

    chain.write_reg(SRC_ROUTE_REQUEST, route_request)
    chain.write_reg(EVENT_FLAGS, chain.read_reg(EVENT_FLAGS) | 0x02)
    delivered, overruns = chain.inject_main_frames_fifo([[0xB0, 0x07, 0x40]], fifo_limit=47)
    assert delivered == 3 and overruns == 0
    chain.step_tcy(COMMAND_SETTLE_TCY)

    stats = chain.read_main_src4382_stats(0)
    assert stats["writes_by_subaddr"][SRC_REG_RX_CONTROL] > 0, stats
    rx_values = chain.read_main_src4382_write_values(0, SRC_REG_RX_CONTROL)
    assert rx_control in rx_values, rx_values

    volume_payload = chain.read_main_dsp_write_payload(0, TAS_REG_VOLUME_COEFF)
    assert volume_payload is not None, (
        f"route request {route_request} updated SRC4382 but did not write "
        f"TAS3108 volume coefficient 0x30"
    )
    assert len(volume_payload) == 4
