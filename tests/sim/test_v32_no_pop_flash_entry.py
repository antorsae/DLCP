"""V3.2 no-pop flash-entry structural tests.

Pins the V3.2 ``flash_entry_quiet_shutdown`` design from
``docs/NO_POP_FIRMWARE_FLASH.md`` so a future change cannot silently:

* drop the helper
* revert the dispatch site to the bare ``call hard_reset``
* downgrade the EEPROM marker from ``0x33`` back to ``0x32``
* slip I2C work into ``hard_reset`` itself (which would turn panic
  callers' broken-state recoveries into hangs)
* reorder ``main_flash_service_46de`` after the helper (which would
  break the EEPROM-marker-first ordering that protects abort/recovery)

The actual audio-pop suppression is unverifiable in sim (gpsim does
not model audio output); operator validation lives in
``docs/HARDWARE_TEST.md`` §"Re-flash pop monitoring".  These tests
cover the structural invariants the spec relies on.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dlcp_fw.paths import V32_MAIN_ASM
from dlcp_fw.sim.v30_symbols import assemble_v30


# ---------------------------------------------------------------------------
# Constants pinned to the no-pop design
# ---------------------------------------------------------------------------

# EEPROM version-marker tuple
# (V3.2 Tier-1: prev no-pop + diag in BANK 2 + cmd21 mask + ACK
#  suppress + always-clear cold init + reset-cause classification
#  + cmd 0x22 reset-flags chain handler + HID cmd 0x44 diag
#  snapshot = 0x03, 0x02, 0x37).
# Bumped 2026-04-20 round-5 from 0x36 → 0x37 to mark images that
# carry the V32_DIAG_TIER1_SPEC.md feature set: 4 reset-cause RAM
# flags classified at cold-init from the RCON snapshot (POR/BOR/
# WDT/SW), a new chain `cmd 0x22` reply burst (BF/28..BF/2B), and
# a new HID `cmd 0x44` diag-snapshot endpoint.
EEPROM_VERSION_TUPLE = (0x03, 0x02, 0x37)

# Expected helper sequence (instruction phase markers, in order).
# Each tuple is (regex, description).
HELPER_SEQUENCE = (
    (r"rcall\s+preset_force_mute", "phase 1: DSP coefficients = 0"),
    (r"clrf\s+ram_0x006,\s*ACCESS",                  "phase 2a: secondary 0x1B value=0"),
    (r"movlw\s+0x1B",                                "phase 2a: secondary register 0x1B"),
    (r"r?call\s+i2c_secondary_dev_write(?:,|\b)",    "phase 2a: write 0x71.0x1B"),
    (r"clrf\s+ram_0x006,\s*ACCESS",                  "phase 2b: secondary 0x1C value=0"),
    (r"movlw\s+0x1C",                                "phase 2b: secondary register 0x1C"),
    (r"r?call\s+i2c_secondary_dev_write(?:,|\b)",    "phase 2b: write 0x71.0x1C"),
    (r"clrf\s+ram_0x006,\s*ACCESS",                  "phase 2c: secondary 0x1D value=0"),
    (r"movlw\s+0x1D",                                "phase 2c: secondary register 0x1D"),
    (r"r?call\s+i2c_secondary_dev_write(?:,|\b)",    "phase 2c: write 0x71.0x1D"),
    (r"bcf\s+LATB,\s*4,\s*ACCESS",                   "phase 3a: amp enable LATB.4 -> 0"),
    (r"bcf\s+LATA,\s*6,\s*ACCESS",                   "phase 3b: LATA.6 -> 0"),
    (r"bcf\s+LATA,\s*3,\s*ACCESS",                   "phase 3c: LATA.3 -> 0 (source select)"),
    (r"bcf\s+LATA,\s*4,\s*ACCESS",                   "phase 3d: LATA.4 -> 0"),
    (r"bcf\s+LATA,\s*5,\s*ACCESS",                   "phase 3e: LATA.5 -> 0"),
    (r"clrf\s+ram_0x004,\s*ACCESS",                  "phase 4a: timer3 high byte = 0"),
    (r"movlw\s+0x64",                                "phase 4b: timer3 low byte = 0x64 (100 ms)"),
    (r"movwf\s+ram_0x003,\s*ACCESS",                 "phase 4c: timer3 reload"),
    (r"r?call\s+timer3_blocking_delay(?:,|\b)",      "phase 4d: 100 ms settle"),
    (r"bcf\s+LATB,\s*3,\s*ACCESS",                   "phase 5: final amp gate LATB.3 -> 0"),
    (r"goto\s+hard_reset",                           "phase 6: now do the RESET"),
)


# ---------------------------------------------------------------------------
# Shared fixture: build V3.2 hex once per module from current source
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def v32_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Per-worker tmp build to avoid xdist races on canonical V32_MAIN_HEX."""
    tmp = tmp_path_factory.mktemp("v32_no_pop")
    hex_out = tmp / "DLCP_Firmware_V3.2.hex"
    assemble_v30(V32_MAIN_ASM, hex_out)
    return hex_out


def _label_offset(text: str, name: str) -> int:
    """Find a label DEFINITION (line-start), not a documentation mention."""
    m = re.search(rf"^{re.escape(name)}:", text, re.MULTILINE)
    if not m:
        raise AssertionError(f"label {name}: not found in source")
    return m.start()


def _label_body(text: str, start_label: str, end_label: str) -> str:
    """Return text between two top-level labels (start inclusive, end exclusive)."""
    start = _label_offset(text, start_label)
    end = _label_offset(text[start + 1:], end_label)
    return text[start:start + 1 + end]


def _strip_comments(asm_body: str) -> str:
    """Remove comment text from each line so pattern matchers don't
    catch documentation references.  The end-of-body label window
    includes the next routine's leading ``; Notes:`` comment block,
    which mentions other routine names that would false-positive on
    forbidden-symbol regexes."""
    out_lines = []
    for line in asm_body.splitlines():
        # Drop the comment (everything from first ';').  Keep the
        # whitespace prefix so instruction patterns still match.
        out_lines.append(line.split(";", 1)[0])
    return "\n".join(out_lines)


# ===========================================================================
# Tier A — structural source assertions
# ===========================================================================


def test_helper_label_exists() -> None:
    """`flash_entry_quiet_shutdown:` must be a top-level label."""
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    assert _label_offset(text, "flash_entry_quiet_shutdown") >= 0


def test_helper_sequence_is_in_order() -> None:
    """The helper body must contain every phase of the spec'd
    sequence in the correct order.

    Each ``HELPER_SEQUENCE`` regex must match within the helper body,
    and matches must appear in the listed order — proving no phase
    has been silently dropped or reordered.  Phase numbering matches
    the spec in docs/NO_POP_FIRMWARE_FLASH.md §Design.
    """
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    body = _label_body(
        text, "flash_entry_quiet_shutdown", "main_core_service_48fe"
    )
    last_pos = 0
    for pattern, desc in HELPER_SEQUENCE:
        m = re.search(pattern, body[last_pos:])
        assert m, (
            f"helper body missing {desc!r} (pattern {pattern!r}); "
            f"either the phase was dropped or it appeared before "
            f"the previous phase (out of order)"
        )
        last_pos += m.end()


def test_helper_terminates_with_goto_hard_reset() -> None:
    """Last instruction in the helper must be ``goto hard_reset`` —
    NOT ``call hard_reset`` (would consume a stack slot we don't
    control on entry to the bootloader) and NOT a fall-through (the
    next label is unrelated and would execute unintended code).
    """
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    body = _label_body(
        text, "flash_entry_quiet_shutdown", "main_core_service_48fe"
    )
    # Strip blank lines and comments to find the LAST executable instruction.
    lines = [
        ln.split(";", 1)[0].rstrip()
        for ln in body.splitlines()
        if ln.strip() and not ln.strip().startswith(";")
    ]
    last = lines[-1].strip()
    assert last == "goto        hard_reset", (
        f"last helper instruction must be exactly 'goto hard_reset'; "
        f"got {last!r}.  call hard_reset would consume a stack slot; "
        f"any other instruction means the helper falls through into "
        f"the next label's body."
    )


def test_dispatch_site_redirects_through_helper() -> None:
    """flow_hid_command_dispatch_13d0 must invoke
    flash_entry_quiet_shutdown via ``goto`` AFTER calling
    main_flash_service_46de (which commits EEPROM[0xFF]=0).

    The EEPROM-marker-first ordering matters: if the helper aborts
    via a bounded I2C timeout, the EEPROM marker is already in place
    so the next reset (forced or spontaneous) still drops into the
    bootloader.  Reordering would break abort/recovery.
    """
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    body = _label_body(
        text, "flow_hid_command_dispatch_13d0", "fw_update_init_sequence"
    )
    # main_flash_service_46de must come BEFORE flash_entry_quiet_shutdown.
    flash_service_pos = body.find("main_flash_service_46de")
    helper_pos = body.find("flash_entry_quiet_shutdown")
    assert flash_service_pos >= 0, "EEPROM marker write missing from dispatch"
    assert helper_pos >= 0, (
        "dispatch site does NOT redirect to flash_entry_quiet_shutdown — "
        "the no-pop entry path has been silently bypassed (likely a "
        "stale `call hard_reset` was reintroduced)"
    )
    assert flash_service_pos < helper_pos, (
        "EEPROM marker (main_flash_service_46de) must commit BEFORE "
        "flash_entry_quiet_shutdown runs; otherwise an abort during "
        "the helper's bounded I2C waits could leave the unit in a "
        "non-bootloader state on the next reset."
    )
    # The transfer must be `goto`, not `call` (the spec mandates this
    # to save a stack slot on the way into the bootloader).
    assert re.search(
        r"goto\s+flash_entry_quiet_shutdown", body
    ), "dispatch site must use `goto flash_entry_quiet_shutdown`, not `call`"


def test_dispatch_site_does_not_call_hard_reset_directly() -> None:
    """The original pre-V3.2 dispatch site landed at ``call hard_reset``
    immediately after the EEPROM marker write.  After the no-pop
    redirect, that exact pattern must NOT exist in the dispatch body.
    A regression test against accidental partial revert.
    """
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    body = _label_body(
        text, "flow_hid_command_dispatch_13d0", "fw_update_init_sequence"
    )
    # Stripped pattern: main_flash_service_46de followed (within ~5
    # instructions) by call hard_reset would be the regression.
    flash_pos = body.find("main_flash_service_46de")
    if flash_pos < 0:
        pytest.fail("EEPROM marker write missing from dispatch")
    window = body[flash_pos:flash_pos + 400]
    assert not re.search(r"call\s+hard_reset", window), (
        "dispatch site has `call hard_reset` after the EEPROM marker — "
        "the no-pop redirect has been reverted (should be `goto "
        "flash_entry_quiet_shutdown` instead)"
    )


def test_hard_reset_remains_minimal() -> None:
    """``hard_reset`` itself must NOT have I2C work added.

    Panic callers (uart_tx_byte_blocking two-strike escalation,
    volume_dsp_write final escalation, v31_hard_reset_jump2) reach
    hard_reset from already-broken states and must not be made to
    touch a potentially-wedged MSSP on the way out — that would turn
    a recoverable panic into a hang.

    The body should consist only of:
      - clrf INTCON (mask interrupts)
      - dw 0xF000 NOP padding
      - reset (PIC18 hardware reset)
      - dw 0xF000 NOP padding
      - return (only reachable if the reset somehow doesn't fire)
    """
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    body = _strip_comments(
        _label_body(text, "hard_reset", "main_i2c_service_48e2")
    )
    # Forbidden in hard_reset: anything that touches I2C, audio,
    # USB, timer hardware, or other side-effecting work.
    forbidden_patterns = (
        (r"i2c_", "I2C call"),
        (r"call\s+preset_", "preset helper call"),
        (r"call\s+volume_dsp_write", "DSP write call"),
        (r"call\s+timer3", "timer3 call"),
        (r"call\s+usb_", "USB helper call"),
        (r"\bSSPCON\b", "MSSP register touch"),
        (r"\bSSPBUF\b", "MSSP buffer touch"),
        (r"\bUCON\b", "USB control register touch"),
    )
    for pattern, label in forbidden_patterns:
        assert not re.search(pattern, body, re.IGNORECASE), (
            f"hard_reset contains {label} (pattern {pattern!r}); "
            f"this turns panic-path callers' broken-state recoveries "
            f"into hangs.  All side-effecting work belongs in "
            f"flash_entry_quiet_shutdown, not hard_reset."
        )
    # Sanity: hard_reset must contain the literal `reset` instruction.
    assert re.search(r"^\s+reset\s*$", body, re.MULTILINE), (
        "hard_reset body lost the `reset` instruction"
    )


def test_helper_calls_preset_force_mute_not_volume_dsp_write() -> None:
    """Helper must use ``preset_force_mute`` (synchronous, single
    coefficient write) NOT ``volume_dsp_write`` (which has its own
    retry + bus-clear + ping escalation that can ITSELF call
    hard_reset, breaking the helper's full-sequence guarantee).
    """
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    body = _label_body(
        text, "flash_entry_quiet_shutdown", "main_core_service_48fe"
    )
    assert "preset_force_mute" in body, (
        "helper must mute the DSP via preset_force_mute"
    )
    assert "volume_dsp_write" not in body, (
        "helper must NOT use volume_dsp_write — its escalation chain "
        "can call hard_reset before the helper's full sequence "
        "completes, defeating the pop-suppression guarantee"
    )


def test_helper_does_not_call_usb_shutdown() -> None:
    """Spec §"What NOT To Do": no ``call usb_shutdown`` before
    ``RESET``.  Pre-disabling UCON lengthens the device-absent window
    and can cause the host to report an unexpected disconnect instead
    of a clean bootloader re-enumeration.  ``RESET`` itself
    disconnects USB cleanly.
    """
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    body = _label_body(
        text, "flash_entry_quiet_shutdown", "main_core_service_48fe"
    )
    assert "usb_shutdown" not in body, (
        "helper must NOT call usb_shutdown — RESET itself disconnects "
        "USB; pre-disabling UCON breaks the bootloader re-enumeration"
    )


def test_helper_does_not_change_oscillator() -> None:
    """Spec §"What NOT To Do": no ``OSCCON.SCS1`` change.  USB needs
    the HS oscillator engaged until RESET fires; switching to INTOSC
    while UCON is alive causes the host to see a hang instead of a
    clean disconnect.
    """
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    body = _label_body(
        text, "flash_entry_quiet_shutdown", "main_core_service_48fe"
    )
    assert not re.search(r"\bOSCCON\b", body), (
        "helper must NOT touch OSCCON — would break USB clean-disconnect"
    )


def test_eeprom_version_marker_is_no_pop_revision() -> None:
    """EEPROM version tuple must be (0x03, 0x02, 0x33) — the no-pop
    revision.  The pre-V3.2 baseline is (0x03, 0x02, 0x32).  Field
    units must be distinguishable so operators can tell whether the
    no-pop helper is in the running image.
    """
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    # Look for the eeprom_data block at org 0xF00000.
    org_pos = text.find("org 0xF00000")
    assert org_pos >= 0, "EEPROM data block missing"
    eeprom_block = text[org_pos:org_pos + 3000]
    expected = "0x{:02X}, 0x{:02X}, 0x{:02X}".format(*EEPROM_VERSION_TUPLE)
    assert expected in eeprom_block, (
        f"EEPROM version marker {EEPROM_VERSION_TUPLE} missing — the "
        f"version byte was downgraded back to the pop-prone baseline. "
        f"Field units would no longer be distinguishable from the "
        f"pre-V3.2 image."
    )
    # And no earlier-revision marker should be present (the new tuple
    # replaces it; multiple presents would be a build error).
    for old in ("0x03, 0x02, 0x32", "0x03, 0x02, 0x33",
                "0x03, 0x02, 0x34", "0x03, 0x02, 0x35",
                "0x03, 0x02, 0x36"):
        assert old not in eeprom_block, (
            f"earlier-revision marker {old!r} present in eeprom_data alongside "
            f"the current {expected} — only one version tuple should exist"
        )


def test_helper_uses_bounded_i2c_via_secondary_write() -> None:
    """The helper relies on V3.1+ bounded I2C waits in
    ``i2c_secondary_dev_write`` and ``i2c_tas3108_coeff_write`` (via
    ``preset_force_mute``).  Both must use ``wait_sen_bounded`` /
    ``wait_pen_bounded`` so a wedged MSSP cannot hang the helper —
    worst case is a single click instead of a permanent hang.

    This test pins the bounded-wait usage in the I2C primitives the
    helper actually calls, so a future refactor that strips the
    bounded variants would be caught here.
    """
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    sec_body = _label_body(text, "i2c_secondary_dev_write", "main_flash_service_46de")
    coeff_body = _label_body(text, "i2c_tas3108_coeff_write", "i2c_secondary_dev_write")
    for label, body in (
        ("i2c_secondary_dev_write", sec_body),
        ("i2c_tas3108_coeff_write", coeff_body),
    ):
        assert "wait_sen_bounded" in body, (
            f"{label} must use wait_sen_bounded — without it a wedged "
            f"MSSP could hang the no-pop helper indefinitely"
        )
        assert "wait_pen_bounded" in body, (
            f"{label} must use wait_pen_bounded — same hang risk on "
            f"the STOP phase"
        )


# ===========================================================================
# Tier B — build verification
# ===========================================================================


def test_v32_assembles_cleanly_with_helper(v32_hex: Path) -> None:
    """Sanity build: V3.2 source assembles with the helper in place
    and produces a non-empty hex artifact.  Catches accidental syntax
    breakage in the helper body.
    """
    assert v32_hex.exists()
    assert v32_hex.stat().st_size > 50_000, (
        f"V3.2 hex unexpectedly small ({v32_hex.stat().st_size} bytes); "
        f"build may have failed silently"
    )


def test_helper_label_resolves_in_lst(v32_hex: Path) -> None:
    """The helper's address must be resolvable from the gpasm listing.

    Listing lives next to the hex (gpasm -o convention).  If the
    helper label was dropped or renamed without updating the dispatch
    site, the build would either fail or the listing would lack the
    symbol — both caught here.
    """
    lst = v32_hex.with_suffix(".lst")
    if not lst.exists():
        pytest.skip(f"no .lst alongside {v32_hex.name}")
    text = lst.read_text(encoding="utf-8", errors="replace")
    # Listing format is varied; just check the label appears as a
    # symbol definition (e.g. "  XXXX flash_entry_quiet_shutdown").
    assert "flash_entry_quiet_shutdown" in text, (
        "flash_entry_quiet_shutdown not found in listing — label was "
        "dropped or the build is stale"
    )
