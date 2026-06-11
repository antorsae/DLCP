"""Regressions for the 2026-06-10 live-flash field incident.

Ledger: docs/V34_FIELD_BUGS_20260610.md.  Four field issues, five defects:

- FIELD-1  flasher post-flash reconnect abort (string-less device never
           classified as app; fixed: identity-probe promotion, event-driven
           wait with 60 s ceiling, --finalize-only recovery)
- FIELD-2  IR profile left on standard-RC5 (consequence of FIELD-1 plus the
           unclamped EEPROM[0x0E] write paths)
- FIELD-3  Preset page row 0 blank after STBY/WAKE while parked on the page
- FIELD-4A preset table apply silently skips NACKed coefficient writes and
           COMMITs/unmutes a wrong DSP image with no fault surfaced (SAFETY)
- FIELD-4B COMMIT restores volume while the post-switch route/mixer DSP
           stage is still queued (audio live through a half-reconfigured DSP)

All tests green: the FIELD-3/4A/4B firmware fixes and the FIELD-1 flasher
fixes are implemented; this file pins them.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

import dlcp_fw.flash.dlcp_main_flash as main_flash
from dlcp_fw.paths import V17_CONTROL_RAM_INC, V173_CONTROL_ASM, V34_MAIN_ASM
from dlcp_fw.sim.v17_symbols import assemble_v17
from dlcp_fw.sim.v30_symbols import assemble_v30
from tests.sim.test_v34_mute_refresh_bug import (
    _boot_v34_main,
    _inject_frame,
)

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain

    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    RustChain = None  # type: ignore[assignment]
    _RUST_CHAIN_IMPORT_ERROR = exc

PRESET_JOB_STATE = 0x2DE
DSP_FAULT_FLAGS = 0x07F
SETUP_PROFILE_RAM = 0x0B8
SETUP_PROFILE_EEPROM = 0x0E
VALID_PROFILE_VALUES = {0x03, 0x04}


# --- shared fixtures ---------------------------------------------------------

@pytest.fixture(scope="module")
def field_main_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v34_field_bugs_main")
    hex_out = tmp / "DLCP_Firmware_V3.4_field.hex"
    assemble_v30(V34_MAIN_ASM, hex_out, output_lst=tmp / "DLCP_Firmware_V3.4_field.lst")
    return hex_out


@pytest.fixture(scope="module")
def field_chain_hexes(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    tmp = tmp_path_factory.mktemp("v34_field_bugs_chain")
    shutil.copy(V17_CONTROL_RAM_INC, tmp / V17_CONTROL_RAM_INC.name)
    control_asm = tmp / V173_CONTROL_ASM.name
    control_asm.write_bytes(V173_CONTROL_ASM.read_bytes())
    control_hex = tmp / "DLCP_Control_V1.73_field.hex"
    assemble_v17(control_asm, control_hex)
    main_hex = tmp / "DLCP_Firmware_V3.4_field.hex"
    assemble_v30(V34_MAIN_ASM, main_hex, output_lst=tmp / "m.lst")
    return control_hex, main_hex


def _biquad_digest(chain, *, unit: int = 0, lo: int = 0x31, hi: int = 0x91) -> str:
    return hashlib.sha256(
        bytes(chain.read_main_dsp_reg(unit, s) for s in range(lo, hi))
    ).hexdigest()[:12]


def _latest_tas30(chain, *, unit: int = 0) -> str | None:
    payloads = chain.read_main_dsp_write_payloads(unit, 0x30)
    return payloads[-1].hex() if payloads else None


def _switch_preset_and_settle(chain, target: int, *, settle_m: int = 60) -> None:
    _inject_frame(chain, 0x20, target)
    chain.step_ticks(settle_m * 1_000_000)
    assert chain.read_main_reg(0, PRESET_JOB_STATE) == 0


# --- FIELD-4A: NACKed table-apply writes silently skipped (SAFETY) ----------

def test_field4a_preset_apply_with_tas_nacks_must_not_unmute_wrong_image(
    field_main_hex: Path,
) -> None:
    chain = _boot_v34_main(field_main_hex)
    chain.step_ticks(8_000_000)

    # Clean references: full A and B images through the fault-free pipeline.
    _switch_preset_and_settle(chain, 1)
    clean_b = _biquad_digest(chain)
    _switch_preset_and_settle(chain, 0)
    clean_a = _biquad_digest(chain)
    assert clean_a != clean_b, "fixture cannot distinguish preset images"

    # Fault variant: I2C data NACKs at switch time (a real-world glitch at
    # the moment of a preset change).
    chain.inject_main_tas3108_data_nack(0, 60)
    _inject_frame(chain, 0x20, 0x01)
    chain.step_ticks(120_000_000)

    digest = _biquad_digest(chain)
    tas30 = _latest_tas30(chain)
    dsp_fault = chain.read_main_reg(0, DSP_FAULT_FLAGS)
    converged = digest == clean_b
    muted_or_faulted = (tas30 in (None, "00000000")) or bool(dsp_fault & 0x40)
    assert converged or muted_or_faulted, (
        "preset apply under NACKs left audio LIVE on a wrong DSP image with "
        f"no fault: digest={digest} (clean_b={clean_b}, clean_a={clean_a}) "
        f"tas30={tas30} dsp_fault=0x{dsp_fault:02X}"
    )


# --- FIELD-4B: unmute must be the LAST stage of the switch pipeline ---------

def test_field4b_no_dsp_coefficient_writes_after_preset_unmute(
    field_main_hex: Path,
) -> None:
    chain = _boot_v34_main(field_main_hex)
    chain.step_ticks(8_000_000)

    # Learn the fully-settled B image once (fault-free).
    _switch_preset_and_settle(chain, 1)
    settled_b = _biquad_digest(chain)
    _switch_preset_and_settle(chain, 0)

    # Re-run the switch with tight sampling: from the first unmuted sample
    # onward, the DSP image must already be final.
    _inject_frame(chain, 0x20, 0x01)
    violations = []
    for i in range(400):
        chain.step_ticks(250_000)
        tas30 = _latest_tas30(chain)
        if tas30 not in (None, "00000000"):
            digest = _biquad_digest(chain)
            if digest != settled_b:
                violations.append((i, tas30, digest))
        if chain.read_main_reg(0, PRESET_JOB_STATE) == 0 and i > 200:
            break
    assert not violations, (
        "DSP coefficients still changing AFTER volume was restored "
        f"(settled_b={settled_b}): {violations[:5]}"
    )


# --- FIELD-3: Preset page row 0 blank after STBY/WAKE while parked ----------

def test_field3_preset_page_row0_survives_standby_wake_while_parked(
    field_chain_hexes: tuple[Path, Path],
) -> None:
    if RustChain is None:  # pragma: no cover
        pytest.fail(f"rust facade not importable: {_RUST_CHAIN_IMPORT_ERROR!r}")
    control_hex, main_hex = field_chain_hexes
    chain = RustChain.from_v171_v32(
        control_hex_path=str(control_hex),
        main_hex_path=str(main_hex),
    )
    assert chain.run_until_connected(limit=300) < 300
    chain.press("RIGHT")
    chain.step_ticks(30_000_000)
    assert chain.lcd_lines()[0].startswith("Preset"), chain.lcd_lines()

    chain.press("STBY")
    assert "ZZZ" in chain.lcd_lines()[0].upper(), chain.lcd_lines()
    chain.press("STBY")
    for _ in range(80):
        if not chain.is_waiting():
            break
        chain.step_ticks(2_000_000)
    chain.step_ticks(30_000_000)

    row0, row1 = chain.lcd_lines()
    assert row0.startswith("Preset"), (
        f"Preset page row 0 lost after standby/wake: {(row0, row1)!r}"
    )
    if row1.strip():
        assert row0.strip(), f"row 1 renders over a blank row 0: {(row0, row1)!r}"


# --- FIELD-2: EEPROM[0x0E] profile byte must never accept garbage -----------

def test_field2_serial_cmd1d_garbage_must_not_corrupt_profile(
    field_main_hex: Path,
) -> None:
    """Green invariant pin: a garbage serial ``B0/1D/0xFF`` must not corrupt
    the profile mirror or its EEPROM[0x0E] backing byte (an out-of-range
    persisted byte becomes 0x03 = standard RC5 at the next boot's clamp,
    killing the Hypex remote).  Sim evidence 2026-06-10: the current V3.4
    serial path already rejects/ignores this vector -- this test guards that
    it stays true.  The HID setup-byte write path
    (``flow_hid_command_dispatch_114a``, report byte -> RAM 0x0B8 unclamped)
    remains an open hardening item tracked in docs/V34_FIELD_BUGS_20260610.md.
    """
    chain = _boot_v34_main(field_main_hex)
    chain.step_ticks(8_000_000)
    before_ram = chain.read_main_reg(0, SETUP_PROFILE_RAM)
    assert before_ram in VALID_PROFILE_VALUES

    _inject_frame(chain, 0x1D, 0xFF)
    chain.step_ticks(120_000_000)  # let any dirty-service persist run

    ram = chain.read_main_reg(0, SETUP_PROFILE_RAM)
    eeprom = chain.read_main_eeprom_byte(0, SETUP_PROFILE_EEPROM)
    assert ram in VALID_PROFILE_VALUES, f"profile RAM mirror corrupted: 0x{ram:02X}"
    assert eeprom in VALID_PROFILE_VALUES, (
        f"EEPROM[0x0E] corrupted: 0x{eeprom:02X} -- next boot clamps this to RC5"
    )


# --- FIELD-1: flasher reconnect classification + recovery (implemented) -----

class _Dev:
    def __init__(self, path: bytes, product: str, serial: str = "") -> None:
        self.path = path
        self.product_string = product
        self.manufacturer_string = ""
        self.serial_number = serial


def test_field1_wait_for_app_accepts_stringless_device_via_identity_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev = _Dev(b"/dev/hid-stringless", "")
    monkeypatch.setattr(main_flash, "enumerate_devices", lambda vid, pid: [dev])
    monkeypatch.setattr(main_flash, "_probe_path_is_app", lambda path: True)
    got = main_flash._wait_for_app(
        vid=0x04D8, pid=0xFF89, serial_number="", timeout_s=2.0
    )
    assert got is dev, "string-less app device must be accepted via identity probe"


def test_field1_wait_for_app_rejects_stringless_non_app_and_hints_finalize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev = _Dev(b"/dev/hid-stringless", "")
    monkeypatch.setattr(main_flash, "enumerate_devices", lambda vid, pid: [dev])
    monkeypatch.setattr(main_flash, "_probe_path_is_app", lambda path: False)
    with pytest.raises(RuntimeError) as err:
        main_flash._wait_for_app(
            vid=0x04D8, pid=0xFF89, serial_number="", timeout_s=0.5
        )
    assert "finalize-only" in str(err.value)


def test_field1_reconnect_ceilings_are_event_driven_defaults() -> None:
    """The wait exits on first positive identification, so the ceiling is a
    failure bound, not a delay -- default must be generous (>= 60 s), not the
    10 s that aborted both live flashes."""
    ap_actions = {a.dest: a.default for a in main_flash.main.__globals__["argparse"].ArgumentParser()._actions}
    # Parse the real parser defaults via a dry argv run instead:
    args = _parse_flasher_defaults()
    assert args.reconnect_timeout_s >= 60.0
    assert args.post_info_timeout_s >= 60.0


def _parse_flasher_defaults():
    import argparse as _argparse

    captured = {}
    real_parse = _argparse.ArgumentParser.parse_args

    def grab(self, argv=None, namespace=None):
        ns = real_parse(self, argv, namespace)
        captured["ns"] = ns
        return ns

    _argparse.ArgumentParser.parse_args = grab
    try:
        try:
            main_flash.main(["--list", "--vid", "0x04D8", "--pid", "0xFF89"])
        except Exception:
            pass
    finally:
        _argparse.ArgumentParser.parse_args = real_parse
    return captured["ns"]


def test_field1_finalize_only_applies_profile_without_flashing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dev = _Dev(b"/dev/hid-app", "DLCP")
    applied = {}

    monkeypatch.setattr(main_flash, "_pick_device", lambda *a, **k: dev)
    monkeypatch.setattr(
        main_flash,
        "_apply_ir_profile_ep0",
        lambda *, vid, pid, path, profile_label: applied.update(
            path=path, profile=profile_label
        )
        or (0x03, 0x04),
    )

    def must_not_flash(*a, **k):  # pragma: no cover - failure path
        raise AssertionError("finalize-only must not flash")

    monkeypatch.setattr(main_flash, "flash_main", must_not_flash)
    rc = main_flash.main(["--finalize-only", "--profile", "hypex"])
    assert rc == 0
    assert applied == {"path": b"/dev/hid-app", "profile": "hypex"}
    out = capsys.readouterr().out
    assert "0x03 -> 0x04" in out


def test_field1_wrapper_forwards_profile_on_finalize_only_and_info_only() -> None:
    """codex review of 947ca22: the wrapper's info-only/finalize-only early
    exits dropped an explicit --profile, silently falling back to the main
    flasher's default.  Both modes honor the flag, so it must forward."""
    import argparse

    from dlcp_fw.flash import dlcp_v34_release_flash as wrapper

    parser = argparse.ArgumentParser()
    for mode_flag in ("--finalize-only", "--info-only"):
        argv_in = [mode_flag, "--profile", "rc5"]
        # parse via the wrapper's real parser by reusing release_main's
        # argument wiring through build_forward_argv
        ns = argparse.Namespace(
            vid=0x04D8,
            pid=0xFF89,
            path=None,
            list=False,
            info_only=(mode_flag == "--info-only"),
            finalize_only=(mode_flag == "--finalize-only"),
            preflight_only=False,
            dry_run=False,
            verbose=False,
            left=False,
            right=False,
            all_ch=None,
            profile="rc5",
            reconnect_timeout_s=None,
        )
        argv = wrapper.build_forward_argv(ns, parser)
        assert ["--profile", "rc5"] == argv[-2:], (mode_flag, argv)


def test_field1_info_only_warns_on_rc5_profile(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dev = _Dev(b"/dev/hid-app", "DLCP")

    class _Input:
        setup_profile = 0x03

    class _Snap:
        input_state = _Input()

    monkeypatch.setattr(main_flash, "_pick_device", lambda *a, **k: dev)
    monkeypatch.setattr(main_flash, "_probe_device_snapshot", lambda **k: _Snap())
    monkeypatch.setattr(main_flash, "_print_device_snapshot", lambda *a, **k: None)
    rc = main_flash.main(["--info-only"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "WARNING" in out and "0x03" in out and "finalize-only" in out


# ---------------------------------------------------------------------------
# Task #8 resolution (2026-06-11): the session-49 "parser loss" mechanism.
# Single-instruction tracing on the run-era binary showed the V3.2 parser
# stall watchdog (main_service_rx_frame_gap) firing MID-FRAME inside a
# normal inter-byte gap: the stock parser idles at fpos=1 after every
# dispatched frame, so the watchdog's 8-bit counter accumulates through
# every inter-frame idle and is never reset when a real frame starts.
# When the carried count is within one inter-byte gap of wrapping, it
# expires between a frame's bytes, resets the frame phase, and the
# remaining bytes are discarded as invalid routes -- the frame silently
# vanishes (session 49 lost a B0/03/02 mute this way).
# ---------------------------------------------------------------------------

RX_FRAME_GAP_TIMEOUT = 0x2F1  # main_rx_frame_gap_timeout (bank2)


def test_v34_frame_dispatches_with_preaccumulated_gap_watchdog(
    field_main_hex: Path,
) -> None:
    """Contract: a frame whose bytes arrive with normal UART spacing must
    dispatch even when the gap-watchdog counter carries a near-wrap value
    from prior inter-frame idle accumulation."""
    chain = _boot_v34_main(field_main_hex)
    chain.step_ticks(8_000_000)
    latch_before = chain.read_main_reg(0, 0x094)
    assert not (latch_before & 0x20)

    # Pre-accumulate the watchdog to the brink, exactly as a long idle does.
    chain.write_main_reg(0, RX_FRAME_GAP_TIMEOUT, 0xFE)
    # Deliver a mute frame with realistic inter-byte spacing (~320 us per
    # byte at 31250 baud ~= 15.4k ticks) so the watchdog polls between bytes.
    chain.inject_main_uart_rx_bytes(0, bytes([0xB0]))
    chain.step_ticks(16_000)
    chain.inject_main_uart_rx_bytes(0, bytes([0x03]))
    chain.step_ticks(16_000)
    chain.inject_main_uart_rx_bytes(0, bytes([0x02]))
    chain.step_ticks(8_000_000)

    latch = chain.read_main_reg(0, 0x094)
    assert latch & 0x20, (
        "mute frame silently discarded: the parser gap watchdog fired "
        f"mid-frame on a pre-accumulated counter (latch=0x{latch:02X})"
    )
