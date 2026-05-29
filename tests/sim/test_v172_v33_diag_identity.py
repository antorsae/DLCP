"""V1.72 CONTROL + V3.3 MAIN Diagnostics identity tests."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dlcp_fw.paths import (
    V17_CONTROL_RAM_INC,
    V172_CONTROL_ASM,
    V32_MAIN_ASM,
    V33_MAIN_ASM,
)
from dlcp_fw.patch.build_v33_release import read_v33_release_revision
from dlcp_fw.sim.v17_symbols import assemble_v17
from dlcp_fw.sim.v30_symbols import assemble_v30


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
DISPLAY_STATE_INDEX_PHYS = 0x0BF

V171_DIAG_PB1_BASE_PHYS = 0x180
V171_DIAG_PB2_BASE_PHYS = 0x18B
V171_DIAG_PRESENT_PHYS = 0x197

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
IR_ADDR_HYPEX = 0x10
IR_CMD_VOL_UP = 0x10
IR_CMD_MUTE = 0x0D
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
def v33_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v172_v33_diag_identity_main")
    hex_out = tmp / "DLCP_Firmware_V3.3.hex"
    assemble_v30(V33_MAIN_ASM, hex_out)
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


def _navigate_to_diag_page(chain, pb_idx: int) -> None:  # type: ignore[no-untyped-def]
    for _ in range(4):
        _tap_key(chain, "RIGHT")
        for _ in range(8):
            chain.step()
    if pb_idx == 1:
        _tap_key(chain, "RIGHT")
        for _ in range(8):
            chain.step()


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
        (IR_PROFILE_POWER_PHYS, 0x0C),
        (IR_PROFILE_VOL_UP_PHYS, IR_CMD_VOL_UP),
        (IR_PROFILE_VOL_DOWN_PHYS, 0x11),
        (IR_PROFILE_INPUT_UP_PHYS, 0x20),
        (IR_PROFILE_INPUT_DOWN_PHYS, 0x21),
        (IR_PROFILE_MUTE_PHYS, IR_CMD_MUTE),
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


def _expected_v33_diag_title(pb_idx: int) -> str:
    rev = read_v33_release_revision(V33_MAIN_ASM)
    return f"PB{pb_idx + 1} OK v3.3 x{rev:02X} "


def test_v33_cmd25_identity_handler_reuses_diag_burst_loop() -> None:
    """MAIN space is tight: cmd 0x25 must stay compact, not unroll 5 frames."""
    text = V33_MAIN_ASM.read_text(encoding="utf-8")
    match = re.search(
        r"cmd25_identity_query_handler:\n(?P<body>.*?)\n; -+\n; diag_send_burst_xx",
        text,
        re.DOTALL,
    )
    assert match is not None, "cmd25_identity_query_handler block not found"
    body = match.group("body")

    assert body.count("rcall       uart_tx_byte_blocking") == 3, (
        "cmd 0x25 should explicitly emit only the BF/4F/id START frame; "
        "the four payload frames must reuse diag_send_burst_xx"
    )
    assert "lfsr        FSR0, 0x0005" in body
    assert "movlw       0x54" in body
    assert "movlw       0x50" in body
    assert "bra         diag_send_burst_xx" in body
    assert "V3.3_IDENTITY_REV_HI" in body
    assert "V3.3_IDENTITY_REV_LO" in body


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
        lambda lcd: (
            chain.read_reg(DISPLAY_STATE_INDEX_PHYS)
            == (STATE_PB1_DIAG if pb_idx == 0 else STATE_PB2_DIAG)
            and lcd[0] == expected
        ),
        limit=700,
    )
    assert lines[0] == expected


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
        lambda lcd: (
            chain.read_reg(DISPLAY_STATE_INDEX_PHYS)
            == (STATE_PB1_DIAG if pb_idx == 0 else STATE_PB2_DIAG)
            and lcd[0] == expected
        ),
        limit=700,
    )

    frames = _inject_diag_ir(chain, IR_CMD_VOL_UP)
    assert chain.read_reg(VOLUME_CACHE_PHYS) == 0x34
    assert (0xB0, 0x07, 0x34) in frames

    frames = _inject_diag_ir(chain, IR_CMD_MUTE)
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
        lambda lcd: (
            chain.read_reg(DISPLAY_STATE_INDEX_PHYS)
            == (STATE_PB1_DIAG if pb_idx == 0 else STATE_PB2_DIAG)
            and lcd[0] == expected
        ),
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
def test_v172_v33_diag_issue_title_suppresses_identity_suffix(
    v172_hex: Path, v33_hex: Path
) -> None:
    chain = _connected_chain(v172_hex, v33_hex)
    chain.write_main_reg(0, DIAG_I_PHYS, 0x02)
    _navigate_to_diag_page(chain, 0)

    lines = _wait_for_lcd(
        chain,
        lambda lcd: (
            chain.read_reg(DISPLAY_STATE_INDEX_PHYS) == STATE_PB1_DIAG
            and chain.read_reg(V171_DIAG_PB1_BASE_PHYS) == 0x02
            and lcd[0].startswith("PB1!")
        ),
        limit=1000,
    )
    assert lines[0] == "PB1! I2 O1      "
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
            chain.read_reg(DISPLAY_STATE_INDEX_PHYS) == STATE_PB1_DIAG
            and (chain.read_reg(V171_DIAG_PRESENT_PHYS) & 0x01)
            and lcd[0] == "PB1 OK          "
        ),
        limit=1400,
    )
    assert lines[0] == "PB1 OK          "
    assert "v3." not in lines[0]
