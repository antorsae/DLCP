"""V1.72 CONTROL + V3.3 MAIN Diagnostics identity tests."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dlcp_fw.paths import (
    V17_CONTROL_RAM_INC,
    V172_CONTROL_ASM,
    V173_CONTROL_ASM,
    V173_CONTROL_HEX,
    V32_MAIN_ASM,
    V33_MAIN_ASM,
    V34_MAIN_ASM,
    V35_MAIN_ASM,
    V35_MAIN_HEX,
)
from dlcp_fw.flash.dlcp_main_flash import (
    detect_static_hex_eeprom_version,
    parse_intel_hex,
)
from dlcp_fw.patch.build_v33_release import read_v33_release_revision
from dlcp_fw.patch.build_v34_release import read_v34_release_revision
from dlcp_fw.patch.build_v35_release import read_v35_release_revision
from dlcp_fw.sim.v17_symbols import assemble_v17
from dlcp_fw.sim.v30_symbols import assemble_v30
from tests.sim.lcd_assertions import assert_lcd_exact, wait_for_lcd_exact


pytestmark = pytest.mark.dual_supported

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain

    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc


_CONTROL_BUTTON_PINS = {
    "RIGHT": ("A", 4),
    "LEFT": ("C", 5),
}

STATE_PB1_DIAG = 4
STATE_PB2_DIAG = 5
STATE_PB1_DIAG_SPLIT = 5
STATE_PB2_DIAG_SPLIT = 6
DISPLAY_STATE_INDEX_PHYS = 0x0BF

V171_DIAG_PB1_BASE_PHYS = 0x180
V171_DIAG_PB2_BASE_PHYS = 0x18B
V171_DIAG_TARGET_PHYS = 0x196
V171_DIAG_PRESENT_PHYS = 0x197
V171_DIAG_FLAGS_PHYS = 0x19C
V171_DIAG_FLAG_DIRTY = 0
V171_HEALTH_AGE_PB1_PHYS = 0x1B0
V171_HEALTH_AGE_PB2_PHYS = 0x1B1
V171_HEALTH_FLAGS_PHYS = 0x1B3
V171_HEALTH_FLAG_DISPLAY_DIRTY = 2
V172_DIAG_ID_PB1_MAJOR_PHYS = 0x245
V172_DIAG_ID_PB1_MINOR_PHYS = 0x246
V172_DIAG_ID_PB1_REV_PHYS = 0x247
V172_DIAG_ID_PB2_MAJOR_PHYS = 0x248
V172_DIAG_ID_PB2_MINOR_PHYS = 0x249
V172_DIAG_ID_PB2_REV_PHYS = 0x24A
V172_DIAG_ID_VALID_MASK_PHYS = 0x24B
V172_DIAG_ID_SEEN_MASK_PHYS = 0x24C
V172_DIAG_ID_PENDING_ID_PHYS = 0x24D
V172_DIAG_ID_FLAGS_PHYS = 0x24E
V172_DIAG_ID_TIMEOUT_PHYS = 0x24F
V172_DIAG_ID_EXPECTED_CMD_PHYS = 0x251
V173_DIAG_ID_PB1_REV_HI_PHYS = 0x26C
V173_DIAG_ID_PB2_REV_HI_PHYS = 0x26D
V172_DIAG_ID_FLAG_PENDING = 0
V172_DIAG_ID_FLAG_TARGET = 1
V172_DIAG_ID_FLAG_RETRIED = 2
V172_DIAG_ID_PENDING_MASK = 1 << V172_DIAG_ID_FLAG_PENDING
V172_DIAG_ID_TARGET_MASK = 1 << V172_DIAG_ID_FLAG_TARGET

DIAG_I_PHYS = 0x2E5

CONTROL_FLAGS_PHYS = 0x01F
CONTROL_CONNECTED_MASK = 0x02
MUTE_MASK = 0x20
PRESET_BIT_MASK = 0x40
VOLUME_CACHE_PHYS = 0x0B9
IR_PROFILE_ADDR_PHYS = 0x020
IR_PROFILE_POWER_PHYS = 0x021
IR_PROFILE_VOL_UP_PHYS = 0x022
IR_PROFILE_VOL_DOWN_PHYS = 0x023
IR_PROFILE_INPUT_UP_PHYS = 0x024
IR_PROFILE_INPUT_DOWN_PHYS = 0x025
IR_PROFILE_MUTE_PHYS = 0x026
MAIN_ACTIVE_FLAGS_PHYS = 0x05E
MAIN_ACTIVE_PRESET_MASK = 0x04
MAIN_ACTIVE_GATE_MASK = 0x08
MAIN_ACTIVE_MUTE_MASK = 0x10
MAIN_SRC_ROUTE_REQUEST_PHYS = 0x093
MAIN_ROUTE_SHADOW_PHYS = 0x0AB
SRC_REG_NON_PCM = 0x12
SRC_REG_RX_STATUS = 0x13
SRC_REG_RX_LOCK = 0x14
TAS_REG_VOLUME_COEFF = 0x30
ONE_S_TICKS = 48_000_000
IR_ADDR_HYPEX = 0x10
IR_CMD_HYPEX_POWER = 0x32
IR_CMD_HYPEX_VOL_UP = 0x33
IR_CMD_HYPEX_VOL_DOWN = 0x34
IR_CMD_HYPEX_MUTE = 0x35
IR_CMD_HYPEX_INPUT_UP = 0x36
IR_CMD_HYPEX_INPUT_DOWN = 0x37
IR_CMD_STD_POWER = 0x0C
IR_CMD_STD_VOL_UP = 0x10
IR_CMD_STD_VOL_DOWN = 0x11
IR_CMD_STD_MUTE = 0x0D
IR_CMD_STD_INPUT_UP = 0x20
IR_CMD_STD_INPUT_DOWN = 0x21
IR_CMD_PRESET_B = 0x39
IR_CMD_STANDBY = 0x3A
IR_CMD_WAKE = 0x3B


@pytest.fixture(scope="module")
def v172_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v172_v33_diag_identity_control")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V172_CONTROL_ASM.name
    asm.write_bytes(V172_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v172.hex"
    assemble_v17(asm, hex_out)
    return hex_out


@pytest.fixture(scope="module")
def v173_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v173_v34_diag_identity_control")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V173_CONTROL_ASM.name
    asm.write_bytes(V173_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v173.hex"
    assemble_v17(asm, hex_out)
    return hex_out


@pytest.fixture(scope="module")
def v33_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v172_v33_diag_identity_main")
    hex_out = tmp / "DLCP_Firmware_V3.3.hex"
    assemble_v30(V33_MAIN_ASM, hex_out)
    return hex_out


@pytest.fixture(scope="module")
def v34_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v173_v34_diag_identity_main")
    hex_out = tmp / "DLCP_Firmware_V3.4.hex"
    assemble_v30(V34_MAIN_ASM, hex_out)
    return hex_out


@pytest.fixture(scope="module")
def v35_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v173_v35_diag_identity_main")
    hex_out = tmp / "DLCP_Firmware_V3.5.hex"
    assemble_v30(V35_MAIN_ASM, hex_out)
    return hex_out


@pytest.fixture(scope="module")
def v32_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v172_v32_diag_identity_main")
    hex_out = tmp / "DLCP_Firmware_V3.2.hex"
    assemble_v30(V32_MAIN_ASM, hex_out)
    return hex_out


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


def _tap_key(chain, key: str) -> None:  # type: ignore[no-untyped-def]
    port, bit = _CONTROL_BUTTON_PINS[key]
    chain.set_control_pin(port, bit, False)
    chain.step_ticks(5_000_000)
    chain.set_control_pin(port, bit, True)
    chain.step_ticks(5_000_000)


def _diag_state_candidates(pb_idx: int) -> tuple[int, int]:
    if pb_idx == 0:
        return (STATE_PB1_DIAG, STATE_PB1_DIAG_SPLIT)
    return (STATE_PB2_DIAG, STATE_PB2_DIAG_SPLIT)


def _is_diag_page(chain, pb_idx: int, lcd=None) -> bool:  # type: ignore[no-untyped-def]
    lines = chain.lcd_lines() if lcd is None else lcd
    return (
        chain.read_reg(DISPLAY_STATE_INDEX_PHYS) in _diag_state_candidates(pb_idx)
        and lines[0].startswith(f"PB{pb_idx + 1}")
    )


def _navigate_to_diag_page(chain, pb_idx: int) -> None:  # type: ignore[no-untyped-def]
    for _ in range(8):
        if _is_diag_page(chain, pb_idx):
            return
        _tap_key(chain, "RIGHT")
        for _ in range(8):
            chain.step()
    if not _is_diag_page(chain, pb_idx):
        pytest.fail(
            f"did not reach PB{pb_idx + 1} Diag; "
            f"lcd={chain.lcd_lines()!r}; "
            f"state=0x{chain.read_reg(DISPLAY_STATE_INDEX_PHYS):02X}"
        )


def _connected_chain(control_hex: Path, main_hex: Path):  # type: ignore[no-untyped-def]
    _require_rust()
    chain = RustChain.from_v171_v32(
        control_hex_path=str(control_hex),
        main_hex_path=str(main_hex),
    )
    chain.run_until_connected(limit=200)
    assert chain.is_connected() and not chain.is_waiting(), (
        f"chain stuck in WAITING/Zzz: lcd={chain.lcd_lines()!r}"
    )
    return chain


def _wait_for_lcd(chain, predicate, *, limit: int = 700):  # type: ignore[no-untyped-def]
    for _ in range(limit):
        lines = chain.lcd_lines()
        if predicate(lines):
            return lines
        chain.step()
    pytest.fail(
        f"LCD condition did not converge; lcd={chain.lcd_lines()!r}; "
        f"state=0x{chain.read_reg(DISPLAY_STATE_INDEX_PHYS):02X}; "
        f"present=0x{chain.read_reg(V171_DIAG_PRESENT_PHYS):02X}"
    )


def _frame_tuple(frame) -> tuple[int, int, int]:  # type: ignore[no-untyped-def]
    return tuple(frame) if isinstance(frame, tuple) else (frame.route, frame.cmd, frame.data)


def _configure_hypex_ir_profile(chain) -> None:  # type: ignore[no-untyped-def]
    for addr, value in (
        (IR_PROFILE_ADDR_PHYS, IR_ADDR_HYPEX),
        (IR_PROFILE_POWER_PHYS, IR_CMD_HYPEX_POWER),
        (IR_PROFILE_VOL_UP_PHYS, IR_CMD_HYPEX_VOL_UP),
        (IR_PROFILE_VOL_DOWN_PHYS, IR_CMD_HYPEX_VOL_DOWN),
        (IR_PROFILE_INPUT_UP_PHYS, IR_CMD_HYPEX_INPUT_UP),
        (IR_PROFILE_INPUT_DOWN_PHYS, IR_CMD_HYPEX_INPUT_DOWN),
        (IR_PROFILE_MUTE_PHYS, IR_CMD_HYPEX_MUTE),
    ):
        chain.write_reg(addr, value)


def _inject_diag_ir(
    chain, cmd: int, *, settle_ticks: int = 12_000_000,
) -> list[tuple[int, int, int]]:  # type: ignore[no-untyped-def]
    before = len(chain.tx_frames())
    chain.inject_decoded_ir_event(addr=IR_ADDR_HYPEX, cmd=cmd)
    chain.step_ticks(settle_ticks)
    return [_frame_tuple(frame) for frame in chain.tx_frames()[before:]]


def _wait_until(
    chain, predicate, *, attempts: int = 120, ticks: int = 2_000_000,
) -> None:  # type: ignore[no-untyped-def]
    for _ in range(attempts):
        if predicate():
            return
        chain.step_ticks(ticks)
    pytest.fail(
        f"condition did not converge; lcd={chain.lcd_lines()!r} "
        f"flags=0x{chain.read_reg(CONTROL_FLAGS_PHYS):02X} "
        f"display_state=0x{chain.read_reg(DISPLAY_STATE_INDEX_PHYS):02X}"
    )


def _main_preset_bits(chain) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    return tuple(
        (chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS_PHYS) & MAIN_ACTIVE_PRESET_MASK) >> 2
        for unit in (0, 1)
    )


def _main_active_gates(chain) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    return tuple(
        (chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS_PHYS) & MAIN_ACTIVE_GATE_MASK) >> 3
        for unit in (0, 1)
    )


def _seed_locked_auto_detect_source(chain) -> None:  # type: ignore[no-untyped-def]
    for unit in (0, 1):
        chain.poke_main_src4382_reg(unit, SRC_REG_RX_STATUS, 0x01)
        chain.poke_main_src4382_reg(unit, SRC_REG_RX_LOCK, 0x00)
        chain.poke_main_src4382_reg(unit, SRC_REG_NON_PCM, 0x00)
    chain.step_ticks(4 * ONE_S_TICKS)


def _assert_connected_live_route_sane(chain, *, expected_route: int | None = None) -> int:  # type: ignore[no-untyped-def]
    assert chain.is_connected() and not chain.is_waiting(), (
        f"CONTROL lost connection or showed WAITING; lcd={chain.lcd_lines()!r}"
    )
    routes = tuple(chain.read_main_reg(unit, MAIN_ROUTE_SHADOW_PHYS) for unit in (0, 1))
    requests = tuple(chain.read_main_reg(unit, MAIN_SRC_ROUTE_REQUEST_PHYS) for unit in (0, 1))
    gates = _main_active_gates(chain)
    mute_bits = tuple(
        chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS_PHYS) & MAIN_ACTIVE_MUTE_MASK
        for unit in (0, 1)
    )
    volumes = tuple(chain.read_main_dsp_write_payload(unit, TAS_REG_VOLUME_COEFF) for unit in (0, 1))

    assert routes[0] != 0 and routes[0] == routes[1], f"bad route shadows: {routes!r}"
    assert requests == routes, f"route request/shadow mismatch: requests={requests!r} routes={routes!r}"
    if expected_route is not None:
        assert routes == (expected_route, expected_route)
    assert gates == (1, 1), f"MAIN gates not both open: {gates!r}"
    assert mute_bits == (0, 0), f"unexpected active mute bits: {mute_bits!r}"
    assert all(payload is not None for payload in volumes), f"missing TAS volume writes: {volumes!r}"
    return routes[0]


def _expected_v33_diag_title(pb_idx: int) -> str:
    rev = read_v33_release_revision(V33_MAIN_ASM)
    return f"PB{pb_idx + 1} OK v3.3 x{rev:02X} "


def _expected_v34_diag_title(pb_idx: int) -> str:
    rev = read_v34_release_revision(V34_MAIN_ASM)
    return f"PB{pb_idx + 1} OK v3.4 {rev:04X}"


def _expected_v35_diag_title(pb_idx: int) -> str:
    rev = read_v35_release_revision(V35_MAIN_ASM)
    return f"PB{pb_idx + 1} OK v3.5 {rev:04X}"


def _expected_canonical_v35_diag_title(pb_idx: int) -> str:
    info = detect_static_hex_eeprom_version(parse_intel_hex(str(V35_MAIN_HEX)))
    assert info is not None, f"V3.5 EEPROM identity missing in {V35_MAIN_HEX}"
    assert (info.major, info.minor) == (0x03, 0x05)
    return f"PB{pb_idx + 1} OK v3.5 {info.revision:04X}"


def _expected_ok_diag_lcd(pb_idx: int, row0: str) -> tuple[str, str]:
    return (row0, "O1              ")


def _diag_identity_cells(pb_idx: int) -> tuple[int, int, int, int]:
    if pb_idx == 0:
        return (
            V172_DIAG_ID_PB1_MAJOR_PHYS,
            V172_DIAG_ID_PB1_MINOR_PHYS,
            V172_DIAG_ID_PB1_REV_PHYS,
            V173_DIAG_ID_PB1_REV_HI_PHYS,
        )
    return (
        V172_DIAG_ID_PB2_MAJOR_PHYS,
        V172_DIAG_ID_PB2_MINOR_PHYS,
        V172_DIAG_ID_PB2_REV_PHYS,
        V173_DIAG_ID_PB2_REV_HI_PHYS,
    )


def _poison_identity_seen_without_valid(chain, pb_idx: int) -> None:  # type: ignore[no-untyped-def]
    mask = 1 << pb_idx
    chain.write_reg(V172_DIAG_ID_VALID_MASK_PHYS, chain.read_reg(V172_DIAG_ID_VALID_MASK_PHYS) & ~mask)
    chain.write_reg(V172_DIAG_ID_SEEN_MASK_PHYS, chain.read_reg(V172_DIAG_ID_SEEN_MASK_PHYS) | mask)
    chain.write_reg(V172_DIAG_ID_FLAGS_PHYS, chain.read_reg(V172_DIAG_ID_FLAGS_PHYS) & ~0x05)
    chain.write_reg(V172_DIAG_ID_TIMEOUT_PHYS, 0x00)
    for addr in _diag_identity_cells(pb_idx):
        chain.write_reg(addr, 0x00)
    chain.write_reg(V171_DIAG_TARGET_PHYS, pb_idx)
    chain.write_reg(V171_DIAG_FLAGS_PHYS, chain.read_reg(V171_DIAG_FLAGS_PHYS) | (1 << V171_DIAG_FLAG_DIRTY))


def _identity_mask(pb_idx: int) -> int:
    return 1 << pb_idx


def _arm_identity_pending(
    chain,  # type: ignore[no-untyped-def]
    pb_idx: int,
    *,
    pending_id: int = 0x12,
    expected_cmd: int = 0x4F,
) -> int:
    mask = _identity_mask(pb_idx)
    chain.write_reg(V172_DIAG_ID_VALID_MASK_PHYS, chain.read_reg(V172_DIAG_ID_VALID_MASK_PHYS) & ~mask)
    chain.write_reg(V172_DIAG_ID_SEEN_MASK_PHYS, chain.read_reg(V172_DIAG_ID_SEEN_MASK_PHYS) & ~mask)
    for addr in _diag_identity_cells(pb_idx):
        chain.write_reg(addr, 0x00)
    query_id = (pending_id & 0x1E) | pb_idx
    flags = V172_DIAG_ID_PENDING_MASK
    if pb_idx:
        flags |= V172_DIAG_ID_TARGET_MASK
    chain.write_reg(V172_DIAG_ID_PENDING_ID_PHYS, query_id)
    chain.write_reg(V172_DIAG_ID_EXPECTED_CMD_PHYS, expected_cmd)
    chain.write_reg(V172_DIAG_ID_TIMEOUT_PHYS, 0x04)
    chain.write_reg(V172_DIAG_ID_FLAGS_PHYS, flags)
    return query_id


def _inject_control_rx_frames(chain, frames: list[tuple[int, int, int]]) -> None:  # type: ignore[no-untyped-def]
    raw: list[int] = []
    for route, cmd, data in frames:
        raw.extend([route & 0xFF, cmd & 0xFF, data & 0xFF])
    assert chain.inject_control_rx_bytes(raw)
    chain.step_ticks(2_000_000)


def _identity_reply_frames(
    query_id: int, *, major: int, minor: int, revision: int
) -> list[tuple[int, int, int]]:
    return [
        (0xBF, 0x4F, query_id),
        (0xBF, 0x50, major & 0x0F),
        (0xBF, 0x51, minor & 0x0F),
        (0xBF, 0x52, (revision >> 4) & 0x0F),
        (0xBF, 0x53, revision & 0x0F),
        (0xBF, 0x54, (revision >> 12) & 0x0F),
        (0xBF, 0x55, (revision >> 8) & 0x0F),
    ]


def test_v33_cmd25_identity_handler_reuses_diag_burst_loop() -> None:
    """MAIN space is tight: cmd 0x25 must stay compact, not unroll 5 frames."""
    text = V33_MAIN_ASM.read_text(encoding="utf-8")
    match = re.search(
        r"cmd25_identity_query_handler:\n(?P<body>.*?)(?:\n; -+\n; cmd 0x26|\n; -+\n; diag_low_nibble_reply_burst)",
        text,
        re.DOTALL,
    )
    assert match is not None, "cmd25_identity_query_handler block not found"
    body = match.group("body")

    assert body.count("rcall       uart_tx_byte_blocking") == 3, (
        "cmd 0x25 should explicitly emit only the BF/4F/id START frame; "
        "the four payload frames must reuse diag_low_nibble_reply_burst"
    )
    assert "lfsr        FSR0, saved_w_b0_phys" in body
    assert "movlw       0x54" in body
    assert "movlw       0x50" in body
    assert "bra         diag_low_nibble_reply_burst" in body
    assert "V3.3_IDENTITY_REV_HI" in body
    assert "V3.3_IDENTITY_REV_LO" in body


def test_v34_cmd25_identity_handler_emits_16bit_revision_nibbles() -> None:
    """V3.4 extends cmd 0x25 to seven frames while preserving the compact burst loop."""
    text = V34_MAIN_ASM.read_text(encoding="utf-8")
    match = re.search(
        r"cmd25_identity_query_handler:\n(?P<body>.*?)(?:\n; -+\n; cmd 0x26|\n; -+\n; diag_low_nibble_reply_burst)",
        text,
        re.DOTALL,
    )
    assert match is not None, "cmd25_identity_query_handler block not found"
    body = match.group("body")

    assert body.count("rcall       uart_tx_byte_blocking") == 2, (
        "cmd 0x25 should explicitly emit only the 4F/id START payload after "
        "the shared BF header helper; "
        "the six payload frames must reuse diag_low_nibble_reply_burst"
    )
    assert "rcall       bf_frame_header_tx" in body
    assert "lfsr        FSR0, saved_w_b0_phys" in body
    assert "movlw       0x56" in body
    assert "movlw       0x50" in body
    assert "bra         diag_low_nibble_reply_burst" in body
    assert "V3.4_IDENTITY_REV_LO_HI" in body
    assert "V3.4_IDENTITY_REV_LO_LO" in body
    assert "V3.4_IDENTITY_REV_HI_HI" in body
    assert "V3.4_IDENTITY_REV_HI_LO" in body


def test_v35_cmd25_identity_handler_emits_16bit_revision_nibbles() -> None:
    """V3.5 keeps the seven-frame cmd 0x25 identity contract on its own source."""
    text = V35_MAIN_ASM.read_text(encoding="utf-8")
    match = re.search(
        r"cmd25_identity_query_handler:\n(?P<body>.*?)(?:\n; -+\n; cmd 0x26|\n; -+\n; diag_low_nibble_reply_burst)",
        text,
        re.DOTALL,
    )
    assert match is not None, "cmd25_identity_query_handler block not found"
    body = match.group("body")

    assert body.count("rcall       uart_tx_byte_blocking") == 2
    assert "rcall       bf_frame_header_tx" in body
    assert "lfsr        FSR0, saved_w_b0_phys" in body
    assert "movlw       0x56" in body
    assert "movlw       0x50" in body
    assert "bra         diag_low_nibble_reply_burst" in body
    assert "V3.5_IDENTITY_REV_LO_HI" in body
    assert "V3.5_IDENTITY_REV_LO_LO" in body
    assert "V3.5_IDENTITY_REV_HI_HI" in body
    assert "V3.5_IDENTITY_REV_HI_LO" in body


def test_v172_source_contains_separate_identity_parser_and_scheduler() -> None:
    text = V172_CONTROL_ASM.read_text(encoding="utf-8")
    assert "v172_bf4f_identity_case_check:" in text
    assert "v171_bf2x_case_check:" in text
    assert text.index("v172_bf4f_identity_case_check:") < text.index(
        "v171_bf2x_case_check:"
    )
    for token in (
        "movlw   0x4F",
        "movlw   0x54",
        "v172_diag_identity_cadence:",
        "v172_diag_identity_send_query:",
        "movlw   0x25",
        "v172_diag_render_identity_suffix",
    ):
        assert token in text


@pytest.mark.slow
def test_v172_boot_splash_renders_baked_release_revision_and_date(v172_hex: Path) -> None:
    _require_rust()
    chain = RustChain.from_v17_control_only(str(v172_hex))
    seen: tuple[str, str] | None = None
    for _ in range(240):
        chain.step_ticks(500_000)
        lines = chain.lcd_lines()
        if lines[0].startswith("Firmware V"):
            seen = lines
            if lines[1].startswith("Rev x"):
                break

    assert seen is not None, "V1.72 boot splash never rendered Firmware row"
    assert seen[0].rstrip() == "Firmware V1.72"
    assert seen[1].startswith("Rev x")
    assert len(seen[1]) == 16
    assert seen[1][4] == "x"
    assert seen[1][7] == " "
    assert seen[1][8:].isdigit()


@pytest.mark.slow
def test_v172_waiting_screen_clears_baked_release_banner_row2(v172_hex: Path) -> None:
    _require_rust()
    chain = RustChain.from_v17_control_only(str(v172_hex))
    saw_banner = False
    for _ in range(260):
        chain.step_ticks(500_000)
        lines = chain.lcd_lines()
        if lines[0].startswith("Firmware V") and lines[1].startswith("Rev x"):
            saw_banner = True
        if lines[0] == "Waiting for DLCP":
            assert saw_banner, "test did not observe the boot release banner first"
            assert lines[1] == " " * 16
            return

    pytest.fail(f"V1.72 control-only run never reached WAITING; lcd={chain.lcd_lines()!r}")


@pytest.mark.slow
@pytest.mark.parametrize("pb_idx", [0, 1])
def test_v172_v33_diag_ok_title_shows_visible_main_identity(
    v172_hex: Path, v33_hex: Path, pb_idx: int
) -> None:
    chain = _connected_chain(v172_hex, v33_hex)
    _navigate_to_diag_page(chain, pb_idx)

    expected = _expected_v33_diag_title(pb_idx)
    lines = _wait_for_lcd(
        chain,
        lambda lcd: _is_diag_page(chain, pb_idx, lcd) and lcd[0] == expected,
        limit=700,
    )
    assert lines[0] == expected


@pytest.mark.slow
@pytest.mark.parametrize("pb_idx", [0, 1])
def test_v173_v34_diag_ok_title_shows_visible_main_identity(
    v173_hex: Path, v34_hex: Path, pb_idx: int
) -> None:
    chain = _connected_chain(v173_hex, v34_hex)
    _navigate_to_diag_page(chain, pb_idx)

    expected = _expected_v34_diag_title(pb_idx)
    lines = _wait_for_lcd(
        chain,
        lambda lcd: _is_diag_page(chain, pb_idx, lcd) and lcd[0] == expected,
        limit=700,
    )
    assert lines[0] == expected


@pytest.mark.slow
@pytest.mark.parametrize("pb_idx", [0, 1])
def test_v173_v35_diag_ok_title_shows_visible_main_identity(
    v173_hex: Path, v35_hex: Path, pb_idx: int
) -> None:
    chain = _connected_chain(v173_hex, v35_hex)
    _navigate_to_diag_page(chain, pb_idx)

    expected = _expected_v35_diag_title(pb_idx)
    lines = _wait_for_lcd(
        chain,
        lambda lcd: _is_diag_page(chain, pb_idx, lcd) and lcd[0] == expected,
        limit=700,
    )
    assert lines[0] == expected


@pytest.mark.slow
@pytest.mark.parametrize("pb_idx", [0, 1])
def test_v173_v35_diag_identity_retries_seen_without_valid_after_runtime_reply(
    v173_hex: Path, v35_hex: Path, pb_idx: int
) -> None:
    chain = _connected_chain(v173_hex, v35_hex)
    _navigate_to_diag_page(chain, pb_idx)

    expected = _expected_v35_diag_title(pb_idx)
    _wait_for_lcd(
        chain,
        lambda lcd: _is_diag_page(chain, pb_idx, lcd) and lcd[0] == expected,
        limit=700,
    )

    _poison_identity_seen_without_valid(chain, pb_idx)
    suffixless = f"PB{pb_idx + 1} OK          "
    _wait_for_lcd(
        chain,
        lambda lcd: _is_diag_page(chain, pb_idx, lcd) and lcd[0] == suffixless,
        limit=1400,
    )

    before = len(chain.tx_frames())
    lines = _wait_for_lcd(
        chain,
        lambda lcd: _is_diag_page(chain, pb_idx, lcd) and lcd[0] == expected,
        limit=2400,
    )

    route = 0xB1 if pb_idx == 0 else 0xB2
    cmd25 = [
        frame
        for frame in chain.tx_frames()[before:]
        if frame[0] == route and frame[1] == 0x25
    ]
    assert cmd25, (
        f"PB{pb_idx + 1} identity should be retried after a healthy "
        f"runtime diagnostics reply; lcd={chain.lcd_lines()!r}"
    )
    assert lines[0] == expected


@pytest.mark.slow
@pytest.mark.parametrize("pb_idx", [0, 1])
def test_v173_v35_diag_entry_invalidates_stale_identity_cache(
    v173_hex: Path, v35_hex: Path, pb_idx: int
) -> None:
    """Diag entry must re-query after a MAIN flash without rebooting CONTROL."""
    chain = _connected_chain(v173_hex, v35_hex)

    if pb_idx == 0:
        stale_major = V172_DIAG_ID_PB1_MAJOR_PHYS
        stale_minor = V172_DIAG_ID_PB1_MINOR_PHYS
        stale_rev = V172_DIAG_ID_PB1_REV_PHYS
        stale_rev_hi = V173_DIAG_ID_PB1_REV_HI_PHYS
    else:
        stale_major = V172_DIAG_ID_PB2_MAJOR_PHYS
        stale_minor = V172_DIAG_ID_PB2_MINOR_PHYS
        stale_rev = V172_DIAG_ID_PB2_REV_PHYS
        stale_rev_hi = V173_DIAG_ID_PB2_REV_HI_PHYS

    chain.write_reg(stale_major, 0x03)
    chain.write_reg(stale_minor, 0x03)
    chain.write_reg(stale_rev, 0x91)
    chain.write_reg(stale_rev_hi, 0x00)
    chain.write_reg(V172_DIAG_ID_VALID_MASK_PHYS, 1 << pb_idx)

    _navigate_to_diag_page(chain, pb_idx)

    expected = _expected_v35_diag_title(pb_idx)
    stale = f"PB{pb_idx + 1} OK v3.3 0091"
    lines = _wait_for_lcd(
        chain,
        lambda lcd: _is_diag_page(chain, pb_idx, lcd) and lcd[0] == expected,
        limit=900,
    )
    assert lines[0] == expected
    assert lines[0] != stale


@pytest.mark.slow
@pytest.mark.parametrize("pb_idx", [0, 1])
def test_v173_v35_canonical_diag_ok_title_shows_visible_main_identity(
    pb_idx: int,
) -> None:
    chain = _connected_chain(V173_CONTROL_HEX, V35_MAIN_HEX)
    _navigate_to_diag_page(chain, pb_idx)

    expected = _expected_ok_diag_lcd(
        pb_idx,
        _expected_canonical_v35_diag_title(pb_idx),
    )
    lines = wait_for_lcd_exact(
        chain,
        expected,
        limit=700,
        context=f"canonical V1.73/V3.5 PB{pb_idx + 1} Diag identity",
    )
    assert_lcd_exact(
        lines,
        expected,
        context=f"canonical V1.73/V3.5 PB{pb_idx + 1} final Diag identity",
    )


@pytest.mark.slow
@pytest.mark.parametrize("pb_idx", [0, 1])
def test_v173_v35_canonical_diag_identity_retries_seen_without_valid_after_runtime_reply(
    pb_idx: int,
) -> None:
    chain = _connected_chain(V173_CONTROL_HEX, V35_MAIN_HEX)
    _navigate_to_diag_page(chain, pb_idx)

    expected = _expected_ok_diag_lcd(pb_idx, _expected_canonical_v35_diag_title(pb_idx))
    wait_for_lcd_exact(
        chain,
        expected,
        limit=700,
        context=f"canonical PB{pb_idx + 1} identity precondition",
    )

    _poison_identity_seen_without_valid(chain, pb_idx)
    suffixless = (f"PB{pb_idx + 1} OK          ", "O1              ")
    wait_for_lcd_exact(
        chain,
        suffixless,
        limit=1400,
        context=f"canonical PB{pb_idx + 1} seen-without-valid poison",
    )

    before = len(chain.tx_frames())
    final_lines = wait_for_lcd_exact(
        chain,
        expected,
        limit=2400,
        context=f"canonical PB{pb_idx + 1} identity retry after poison",
    )

    route = 0xB1 if pb_idx == 0 else 0xB2
    assert any(
        frame[0] == route and frame[1] == 0x25
        for frame in chain.tx_frames()[before:]
    )
    assert_lcd_exact(final_lines, expected)


@pytest.mark.slow
@pytest.mark.parametrize("pb_idx", [0, 1])
@pytest.mark.parametrize(
    ("case", "frames", "pending_after"),
    [
        (
            "wrong-start-id-keeps-pending",
            [(0xBF, 0x4F, 0x13)],
            True,
        ),
        (
            "out-of-order-aborts",
            [(0xBF, 0x4F, 0x12), (0xBF, 0x52, 0x03)],
            False,
        ),
        (
            "bad-nibble-aborts-with-filename-traffic",
            [(0xBF, 0x2D, 0x12), (0xBF, 0x4F, 0x12), (0xBF, 0x50, 0x10), (0xBF, 0x4E, 0x12)],
            False,
        ),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_v173_v35_canonical_diag_identity_malformed_replies_do_not_validate_or_poison_retry(
    pb_idx: int,
    case: str,
    frames: list[tuple[int, int, int]],
    pending_after: bool,
) -> None:
    chain = _connected_chain(V173_CONTROL_HEX, V35_MAIN_HEX)
    _navigate_to_diag_page(chain, pb_idx)
    expected = _expected_ok_diag_lcd(pb_idx, _expected_canonical_v35_diag_title(pb_idx))
    wait_for_lcd_exact(
        chain,
        expected,
        limit=700,
        context=f"canonical PB{pb_idx + 1} identity precondition for {case}",
    )

    query_id = _arm_identity_pending(chain, pb_idx, pending_id=0x12)
    concrete_frames = [
        (
            route,
            cmd,
            (query_id ^ 0x02)
            if case == "wrong-start-id-keeps-pending"
            else query_id
            if (route, cmd, data) == (0xBF, 0x4F, 0x12)
            else data,
        )
        for route, cmd, data in frames
    ]
    _inject_control_rx_frames(chain, concrete_frames)

    mask = _identity_mask(pb_idx)
    assert not (chain.read_reg(V172_DIAG_ID_VALID_MASK_PHYS) & mask)
    assert bool(chain.read_reg(V172_DIAG_ID_FLAGS_PHYS) & V172_DIAG_ID_PENDING_MASK) is pending_after
    assert all(chain.read_reg(addr) == 0x00 for addr in _diag_identity_cells(pb_idx))

    if pending_after:
        chain.write_reg(
            V172_DIAG_ID_FLAGS_PHYS,
            chain.read_reg(V172_DIAG_ID_FLAGS_PHYS) & ~V172_DIAG_ID_PENDING_MASK,
        )

    final_lines = wait_for_lcd_exact(
        chain,
        expected,
        limit=2400,
        context=f"canonical PB{pb_idx + 1} identity recovery after {case}",
    )
    assert_lcd_exact(final_lines, expected)


@pytest.mark.slow
@pytest.mark.parametrize("pb_idx", [0, 1])
def test_v173_identity_parser_waits_for_v35_rev16_tail_before_valid(
    v173_hex: Path, v35_hex: Path, pb_idx: int
) -> None:
    chain = _connected_chain(v173_hex, v35_hex)
    query_id = _arm_identity_pending(chain, pb_idx, pending_id=0x12)
    frames = _identity_reply_frames(query_id, major=0x03, minor=0x05, revision=0x0123)

    _inject_control_rx_frames(chain, frames[:5])

    mask = _identity_mask(pb_idx)
    assert not (chain.read_reg(V172_DIAG_ID_VALID_MASK_PHYS) & mask)
    assert chain.read_reg(V172_DIAG_ID_EXPECTED_CMD_PHYS) == 0x54
    assert chain.read_reg(V172_DIAG_ID_FLAGS_PHYS) & V172_DIAG_ID_PENDING_MASK
    assert all(chain.read_reg(addr) == 0x00 for addr in _diag_identity_cells(pb_idx))

    _inject_control_rx_frames(chain, frames[5:])

    major, minor, rev_lo, rev_hi = _diag_identity_cells(pb_idx)
    assert chain.read_reg(V172_DIAG_ID_VALID_MASK_PHYS) & mask
    assert chain.read_reg(V172_DIAG_ID_SEEN_MASK_PHYS) & mask
    assert not (chain.read_reg(V172_DIAG_ID_FLAGS_PHYS) & V172_DIAG_ID_PENDING_MASK)
    assert [chain.read_reg(addr) for addr in (major, minor, rev_lo, rev_hi)] == [
        0x03,
        0x05,
        0x23,
        0x01,
    ]


@pytest.mark.slow
@pytest.mark.parametrize("pb_idx", [0, 1])
def test_v173_identity_parser_keeps_legacy_v33_bf53_commit_path(
    v173_hex: Path, v35_hex: Path, pb_idx: int
) -> None:
    chain = _connected_chain(v173_hex, v35_hex)
    query_id = _arm_identity_pending(chain, pb_idx, pending_id=0x12)
    frames = _identity_reply_frames(query_id, major=0x03, minor=0x03, revision=0x0091)

    _inject_control_rx_frames(chain, frames[:5])

    mask = _identity_mask(pb_idx)
    major, minor, rev_lo, rev_hi = _diag_identity_cells(pb_idx)
    assert chain.read_reg(V172_DIAG_ID_VALID_MASK_PHYS) & mask
    assert not (chain.read_reg(V172_DIAG_ID_FLAGS_PHYS) & V172_DIAG_ID_PENDING_MASK)
    assert [chain.read_reg(addr) for addr in (major, minor, rev_lo, rev_hi)] == [
        0x03,
        0x03,
        0x91,
        0x00,
    ]


def test_v173_identity_parser_source_gate_is_v34_plus_not_v34_only() -> None:
    text = V173_CONTROL_ASM.read_text(encoding="utf-8")
    match = re.search(
        r"v172_bf4f_payload_rev_lo:\n(?P<body>.*?)\nv172_bf4f_commit_rev8:",
        text,
        re.DOTALL,
    )
    assert match is not None, "BF/4F revision-low parser block not found"
    body = match.group("body")

    assert "cpfslt  v172_diag_id_tmp_minor_b2, BANKED" in body
    assert not re.search(
        r"movlw\s+0x04\s+cpfseq\s+v172_diag_id_tmp_minor_b2,\s+BANKED\s+bra\s+v172_bf4f_commit_rev8",
        body,
    )


@pytest.mark.slow
@pytest.mark.parametrize("pb_idx", [0, 1])
@pytest.mark.parametrize(
    ("age", "label"),
    [(0x03, "old"), (0x0A, "lost")],
    ids=["old", "lost"],
)
def test_v173_v35_canonical_diag_old_lost_rows_clear_identity_suffix(
    pb_idx: int,
    age: int,
    label: str,
) -> None:
    chain = _connected_chain(V173_CONTROL_HEX, V35_MAIN_HEX)
    _navigate_to_diag_page(chain, pb_idx)
    expected = _expected_ok_diag_lcd(pb_idx, _expected_canonical_v35_diag_title(pb_idx))
    wait_for_lcd_exact(
        chain,
        expected,
        limit=700,
        context=f"canonical PB{pb_idx + 1} identity precondition for {label}",
    )

    chain.set_blackout(True)
    age_addr = V171_HEALTH_AGE_PB1_PHYS if pb_idx == 0 else V171_HEALTH_AGE_PB2_PHYS
    chain.write_reg(age_addr, age)
    chain.write_reg(
        V171_HEALTH_FLAGS_PHYS,
        chain.read_reg(V171_HEALTH_FLAGS_PHYS) | (1 << V171_HEALTH_FLAG_DISPLAY_DIRTY),
    )

    expected_row0 = f"PB{pb_idx + 1} {label}".ljust(16)
    lines = wait_for_lcd_exact(
        chain,
        (expected_row0, " " * 16),
        limit=700,
        context=f"canonical PB{pb_idx + 1} {label} row clears identity suffix",
    )

    mask = _identity_mask(pb_idx)
    assert_lcd_exact(lines, (expected_row0, " " * 16))
    assert not (chain.read_reg(V172_DIAG_ID_VALID_MASK_PHYS) & mask)
    assert "v3." not in lines[0]


@pytest.mark.slow
def test_v173_v35_canonical_pb2_old_main_reentry_does_not_restore_stale_suffix() -> None:
    chain = _connected_chain(V173_CONTROL_HEX, V35_MAIN_HEX)
    pb_idx = 1
    _navigate_to_diag_page(chain, pb_idx)
    expected = _expected_ok_diag_lcd(pb_idx, _expected_canonical_v35_diag_title(pb_idx))
    wait_for_lcd_exact(
        chain,
        expected,
        limit=700,
        context="canonical PB2 identity precondition before old-MAIN re-entry",
    )

    chain.set_blackout(True)
    chain.write_reg(V171_HEALTH_AGE_PB2_PHYS, 0x03)
    chain.write_reg(
        V171_HEALTH_FLAGS_PHYS,
        chain.read_reg(V171_HEALTH_FLAGS_PHYS) | (1 << V171_HEALTH_FLAG_DISPLAY_DIRTY),
    )
    old_row = ("PB2 old         ", " " * 16)
    wait_for_lcd_exact(
        chain,
        old_row,
        limit=700,
        context="canonical PB2 old row before page re-entry",
    )

    _tap_key(chain, "RIGHT")
    assert not _is_diag_page(chain, pb_idx) or chain.lcd_lines() == old_row
    _navigate_to_diag_page(chain, pb_idx)
    lines = wait_for_lcd_exact(
        chain,
        old_row,
        limit=900,
        context="canonical PB2 old row after page re-entry",
    )

    assert_lcd_exact(lines, old_row)
    assert "v3." not in lines[0]
    assert not (chain.read_reg(V172_DIAG_ID_VALID_MASK_PHYS) & _identity_mask(pb_idx))


@pytest.mark.slow
@pytest.mark.parametrize("pb_idx", [0, 1])
def test_v173_v35_canonical_diag_entry_invalidates_stale_identity_cache(
    pb_idx: int,
) -> None:
    """Canonical artifacts must replace stale healthy PB identity text on Diag entry."""
    chain = _connected_chain(V173_CONTROL_HEX, V35_MAIN_HEX)

    if pb_idx == 0:
        stale_major = V172_DIAG_ID_PB1_MAJOR_PHYS
        stale_minor = V172_DIAG_ID_PB1_MINOR_PHYS
        stale_rev = V172_DIAG_ID_PB1_REV_PHYS
        stale_rev_hi = V173_DIAG_ID_PB1_REV_HI_PHYS
    else:
        stale_major = V172_DIAG_ID_PB2_MAJOR_PHYS
        stale_minor = V172_DIAG_ID_PB2_MINOR_PHYS
        stale_rev = V172_DIAG_ID_PB2_REV_PHYS
        stale_rev_hi = V173_DIAG_ID_PB2_REV_HI_PHYS

    chain.write_reg(stale_major, 0x03)
    chain.write_reg(stale_minor, 0x03)
    chain.write_reg(stale_rev, 0x91)
    chain.write_reg(stale_rev_hi, 0x00)
    chain.write_reg(V172_DIAG_ID_VALID_MASK_PHYS, 1 << pb_idx)

    _navigate_to_diag_page(chain, pb_idx)

    expected = _expected_ok_diag_lcd(
        pb_idx,
        _expected_canonical_v35_diag_title(pb_idx),
    )
    stale = f"PB{pb_idx + 1} OK v3.3 0091"
    timeline: list[tuple[str, str]] = []
    final_lines: tuple[str, str] | None = None
    for _ in range(900):
        lines = chain.lcd_lines()
        if not timeline or timeline[-1] != lines:
            timeline.append(lines)
        if lines == expected:
            final_lines = lines
            break
        chain.step()

    assert final_lines == expected, (
        f"canonical V1.73/V3.5 PB{pb_idx + 1} Diag identity did not settle; "
        f"expected={expected!r}; tail={timeline[-12:]!r}"
    )
    assert_lcd_exact(
        final_lines,
        expected,
        context=f"canonical stale PB{pb_idx + 1} identity replaced",
    )
    assert final_lines[0] != stale
    assert not any(lines[0] == stale for lines in timeline[-12:]), (
        f"stale healthy identity remained visible after settle window: "
        f"stale={stale!r}; tail={timeline[-12:]!r}"
    )


@pytest.mark.slow
def test_v173_v34_auto_detect_live_route_survives_diag_identity_happy_path(
    v173_hex: Path, v34_hex: Path
) -> None:
    chain = _connected_chain(v173_hex, v34_hex)
    _seed_locked_auto_detect_source(chain)

    route = _assert_connected_live_route_sane(chain)
    chain.step_ticks(10 * ONE_S_TICKS)
    _assert_connected_live_route_sane(chain, expected_route=route)

    _navigate_to_diag_page(chain, 0)
    expected_pb1 = _expected_v34_diag_title(0)
    lines = _wait_for_lcd(
        chain,
        lambda lcd: _is_diag_page(chain, 0, lcd) and lcd[0] == expected_pb1,
        limit=700,
    )
    assert lines[0] == expected_pb1
    chain.step_ticks(3 * ONE_S_TICKS)
    assert chain.lcd_lines()[0] == expected_pb1
    _assert_connected_live_route_sane(chain, expected_route=route)

    _tap_key(chain, "RIGHT")
    for _ in range(8):
        chain.step()
    expected_pb2 = _expected_v34_diag_title(1)
    lines = _wait_for_lcd(
        chain,
        lambda lcd: _is_diag_page(chain, 1, lcd) and lcd[0] == expected_pb2,
        limit=700,
    )
    assert lines[0] == expected_pb2
    chain.step_ticks(3 * ONE_S_TICKS)
    assert chain.lcd_lines()[0] == expected_pb2
    _assert_connected_live_route_sane(chain, expected_route=route)


@pytest.mark.slow
@pytest.mark.parametrize("pb_idx", [0, 1])
def test_v172_v33_diag_page_dispatches_ir_volume_mute_and_preset(
    v172_hex: Path, v33_hex: Path, pb_idx: int
) -> None:
    """Identity-enabled Diag pages must still run normal IR dispatch."""
    chain = _connected_chain(v172_hex, v33_hex)
    _configure_hypex_ir_profile(chain)
    chain.write_reg(VOLUME_CACHE_PHYS, 0x33)
    chain.write_reg(
        CONTROL_FLAGS_PHYS,
        chain.read_reg(CONTROL_FLAGS_PHYS) & ~MUTE_MASK & ~PRESET_BIT_MASK,
    )
    _navigate_to_diag_page(chain, pb_idx)

    expected = _expected_v33_diag_title(pb_idx)
    _wait_for_lcd(
        chain,
        lambda lcd: _is_diag_page(chain, pb_idx, lcd) and lcd[0] == expected,
        limit=700,
    )

    frames = _inject_diag_ir(chain, IR_CMD_HYPEX_VOL_UP)
    assert chain.read_reg(VOLUME_CACHE_PHYS) == 0x34
    assert (0xB0, 0x07, 0x34) in frames

    frames = _inject_diag_ir(chain, IR_CMD_HYPEX_MUTE)
    assert chain.read_reg(CONTROL_FLAGS_PHYS) & MUTE_MASK
    assert (0xB0, 0x03, 0x02) in frames

    frames = _inject_diag_ir(chain, IR_CMD_PRESET_B, settle_ticks=20_000_000)
    assert chain.read_reg(CONTROL_FLAGS_PHYS) & PRESET_BIT_MASK
    assert (0xB0, 0x20, 0x01) in frames
    _wait_until(chain, lambda: _main_preset_bits(chain) == (1, 1), attempts=160)

    assert chain.lcd_lines()[0].startswith(f"PB{pb_idx + 1}"), (
        f"IR volume/mute/preset should not navigate away from Diag; "
        f"lcd={chain.lcd_lines()!r}"
    )


@pytest.mark.slow
@pytest.mark.parametrize("pb_idx", [0, 1])
def test_v173_v34_diag_page_dispatches_hypex_ir_volume_mute_and_preset(
    v173_hex: Path, v34_hex: Path, pb_idx: int
) -> None:
    """V1.73/V3.4 must dispatch the real Hypex profile command bytes."""
    chain = _connected_chain(v173_hex, v34_hex)
    _configure_hypex_ir_profile(chain)
    chain.write_reg(VOLUME_CACHE_PHYS, 0x33)
    chain.write_reg(
        CONTROL_FLAGS_PHYS,
        chain.read_reg(CONTROL_FLAGS_PHYS) & ~MUTE_MASK & ~PRESET_BIT_MASK,
    )
    _navigate_to_diag_page(chain, pb_idx)

    expected = _expected_v34_diag_title(pb_idx)
    _wait_for_lcd(
        chain,
        lambda lcd: _is_diag_page(chain, pb_idx, lcd) and lcd[0] == expected,
        limit=700,
    )

    frames = _inject_diag_ir(chain, IR_CMD_HYPEX_VOL_UP)
    assert chain.read_reg(VOLUME_CACHE_PHYS) == 0x34
    assert (0xB0, 0x07, 0x34) in frames

    frames = _inject_diag_ir(chain, IR_CMD_HYPEX_MUTE)
    assert chain.read_reg(CONTROL_FLAGS_PHYS) & MUTE_MASK
    assert (0xB0, 0x03, 0x02) in frames

    frames = _inject_diag_ir(chain, IR_CMD_PRESET_B, settle_ticks=20_000_000)
    assert chain.read_reg(CONTROL_FLAGS_PHYS) & PRESET_BIT_MASK
    assert (0xB0, 0x20, 0x01) in frames
    _wait_until(chain, lambda: _main_preset_bits(chain) == (1, 1), attempts=160)

    assert chain.lcd_lines()[0].startswith(f"PB{pb_idx + 1}"), (
        f"IR volume/mute/preset should not navigate away from Diag; "
        f"lcd={chain.lcd_lines()!r}"
    )


@pytest.mark.slow
@pytest.mark.parametrize("pb_idx", [0, 1])
def test_v172_v33_diag_page_dispatches_ir_standby_and_wake(
    v172_hex: Path, v33_hex: Path, pb_idx: int
) -> None:
    """Identity-enabled Diag pages must not starve IR standby/wake."""
    chain = _connected_chain(v172_hex, v33_hex)
    _configure_hypex_ir_profile(chain)
    _navigate_to_diag_page(chain, pb_idx)

    expected = _expected_v33_diag_title(pb_idx)
    _wait_for_lcd(
        chain,
        lambda lcd: _is_diag_page(chain, pb_idx, lcd) and lcd[0] == expected,
        limit=700,
    )

    standby_frames = _inject_diag_ir(chain, IR_CMD_STANDBY, settle_ticks=20_000_000)
    assert (0xB0, 0x03, 0x00) in standby_frames
    _wait_until(chain, lambda: "ZZZ" in chain.lcd_lines()[0].upper(), attempts=120)
    _wait_until(chain, lambda: _main_active_gates(chain) == (0, 0), attempts=180)

    wake_frames = _inject_diag_ir(chain, IR_CMD_WAKE, settle_ticks=20_000_000)
    assert (0xB0, 0x03, 0x01) in wake_frames
    _wait_until(
        chain,
        lambda: (
            chain.is_connected()
            and bool(chain.read_reg(CONTROL_FLAGS_PHYS) & CONTROL_CONNECTED_MASK)
            and "ZZZ" not in chain.lcd_lines()[0].upper()
        ),
        attempts=180,
    )
    _wait_until(chain, lambda: _main_active_gates(chain) == (1, 1), attempts=240)


@pytest.mark.slow
@pytest.mark.parametrize("pb_idx", [0, 1])
def test_v173_v34_diag_page_dispatches_ir_standby_and_wake(
    v173_hex: Path, v34_hex: Path, pb_idx: int
) -> None:
    """V1.73/V3.4 Diag pages must not starve explicit IR standby/wake."""
    chain = _connected_chain(v173_hex, v34_hex)
    _configure_hypex_ir_profile(chain)
    _navigate_to_diag_page(chain, pb_idx)

    expected = _expected_v34_diag_title(pb_idx)
    _wait_for_lcd(
        chain,
        lambda lcd: _is_diag_page(chain, pb_idx, lcd) and lcd[0] == expected,
        limit=700,
    )

    standby_frames = _inject_diag_ir(chain, IR_CMD_STANDBY, settle_ticks=20_000_000)
    assert (0xB0, 0x03, 0x00) in standby_frames
    _wait_until(chain, lambda: "ZZZ" in chain.lcd_lines()[0].upper(), attempts=120)
    _wait_until(chain, lambda: _main_active_gates(chain) == (0, 0), attempts=180)

    wake_frames = _inject_diag_ir(chain, IR_CMD_WAKE, settle_ticks=20_000_000)
    assert (0xB0, 0x03, 0x01) in wake_frames
    _wait_until(
        chain,
        lambda: (
            chain.is_connected()
            and bool(chain.read_reg(CONTROL_FLAGS_PHYS) & CONTROL_CONNECTED_MASK)
            and "ZZZ" not in chain.lcd_lines()[0].upper()
        ),
        attempts=180,
    )
    _wait_until(chain, lambda: _main_active_gates(chain) == (1, 1), attempts=240)


@pytest.mark.slow
@pytest.mark.parametrize(
    ("profile_byte", "expected_profile"),
    [
        (
            0x04,
            [
                IR_ADDR_HYPEX,
                IR_CMD_HYPEX_POWER,
                IR_CMD_HYPEX_VOL_UP,
                IR_CMD_HYPEX_VOL_DOWN,
                IR_CMD_HYPEX_INPUT_UP,
                IR_CMD_HYPEX_INPUT_DOWN,
                IR_CMD_HYPEX_MUTE,
            ],
        ),
        (
            0x03,
            [
                0x00,
                IR_CMD_STD_POWER,
                IR_CMD_STD_VOL_UP,
                IR_CMD_STD_VOL_DOWN,
                IR_CMD_STD_INPUT_UP,
                IR_CMD_STD_INPUT_DOWN,
                IR_CMD_STD_MUTE,
            ],
        ),
    ],
)
def test_v173_v34_boot_loads_ir_profile_from_main_setup_byte(
    v173_hex: Path, v34_hex: Path, profile_byte: int, expected_profile: list[int]
) -> None:
    chain = RustChain.from_v171_v32(
        control_hex_path=str(v173_hex),
        main_hex_path=str(v34_hex),
    )
    for unit in (0, 1):
        chain.write_main_eeprom_byte(unit, 0x0E, profile_byte)
    assert chain.run_until_connected(limit=300) < 300

    actual = [chain.read_reg(addr) for addr in range(0x020, 0x027)]
    assert actual == expected_profile
    assert chain.read_reg(0x0A7) == profile_byte


@pytest.mark.slow
def test_v172_v33_diag_issue_title_suppresses_identity_suffix(
    v172_hex: Path, v33_hex: Path
) -> None:
    chain = _connected_chain(v172_hex, v33_hex)
    chain.write_main_reg(0, DIAG_I_PHYS, 0x02)
    _navigate_to_diag_page(chain, 0)

    lines = _wait_for_lcd(
        chain,
        lambda lcd: (
            _is_diag_page(chain, 0, lcd)
            and chain.read_reg(V171_DIAG_PB1_BASE_PHYS) == 0x02
            and lcd[0].startswith("PB1!")
        ),
        limit=1000,
    )
    assert lines[0].startswith("PB1! I2")
    assert len(lines[0]) == 16
    assert "v3.3" not in lines[0]
    assert "x" not in lines[0][4:]


@pytest.mark.slow
def test_v172_v32_diag_is_backward_compatible_without_identity_reply(
    v172_hex: Path, v32_hex: Path
) -> None:
    chain = _connected_chain(v172_hex, v32_hex)
    _navigate_to_diag_page(chain, 0)

    lines = _wait_for_lcd(
        chain,
        lambda lcd: (
            _is_diag_page(chain, 0, lcd)
            and (chain.read_reg(V171_DIAG_PRESENT_PHYS) & 0x01)
            and lcd[0] == "PB1 OK          "
        ),
        limit=1400,
    )
    assert lines[0] == "PB1 OK          "
    assert "v3." not in lines[0]
