"""End-to-end V3.2 release flasher integration test against a sim chain.

Runs ``dlcp_v32_release_flash.main(["--right", ...])`` against a
pre-overlaid V1.71+2x V3.2 chain and verifies post-flash state:

  * Preset A flash table at 0x5600..0x5FFF matches the capture.
  * Preset B flash table at 0x4C00..0x55FF matches the capture.
  * Preset A EEPROM filename slot at 0x60..0x7D matches the capture sidecar.
  * Preset B EEPROM filename slot at 0x83..0xA0 matches.
  * Active route mapping is "R" (--right was passed).

The fixture pre-overlays the V3.2 hex with the captures BEFORE
constructing the chain (per the constraint documented in
``sim_backend.SimHidBackend._handle_bootloader_stream``: cmd 0x40
stream bytes are not patched into the running firmware's flash, so
the chain must already match the post-flash image).
"""

from __future__ import annotations

import pytest

from dlcp_fw.paths import (
    ARTIFACTS_DIR,
    STOCK_MAIN_COMBINED_HEX,
    V171_CONTROL_HEX,
    V32_MAIN_HEX,
)


try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain

    _RUST_OK = True
    _RUST_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_OK = False
    _RUST_ERROR = exc


from dlcp_fw.flash.sim_backend import (
    SimUsbHub,
    install_sim_hub,
    make_sim_hub,
)


pytestmark = pytest.mark.dual_supported


CAPTURE_DIR = ARTIFACTS_DIR / "LX521.4"
CAPTURE_A_BIN = CAPTURE_DIR / "LX521.4_22MG10F-v5.bin"
CAPTURE_A_META = CAPTURE_DIR / "LX521.4_22MG10F-v5.json"
CAPTURE_B_BIN = CAPTURE_DIR / "LX521.4_22MG10F-v7.bin"
CAPTURE_B_META = CAPTURE_DIR / "LX521.4_22MG10F-v7.json"


# Cross-checked vs dlcp_main_flash.py / read_coeffs.py constants.
_PRESET_A_FLASH_BASE = 0x5600
_PRESET_B_FLASH_BASE = 0x4C00
_PRESET_TABLE_SIZE = 0x0A00
_PRESET_A_EEPROM_BASE = 0x60
_PRESET_B_EEPROM_BASE = 0x83
_FILENAME_LEN = 0x1E
_ROUTE_RAM_BASE = 0x60
_ROUTE_SOURCE_RAM_BASE = 0xA5
_ROUTE_LEN = 0x06
_ROUTE_VALUE_L = 0x00
_ROUTE_VALUE_R = 0x01
_ACTIVE_FLAGS_ADDR = 0x05E
_ACTIVE_PRESET_MASK = 0x04
_FILENAME_RAM_BASE = 0x2C0
_COMPUTED_VOLUME_RAM_BASE = 0x06E
_LOGICAL_VOLUME_RAM_BASE = 0x066
_INPUT_SELECT_RAM = 0x099
_INPUT_SELECT_MIRROR_RAM = 0x0B3
_SETUP_PROFILE_RAM = 0x0B8
_USER_VOLUME_MINUS_30 = (0xFF, 0xFF, 0xFF, 0xE2)
_USER_INPUT_COAX_2 = 0x03
_USER_SETUP_PROFILE_SENTINEL = 0x03
_PRESET_JOB_STATE = 0x2DE
_PRESET_JOB_IDLE = 0
_CONTROL_FLAGS_ADDR = 0x01F
_CONTROL_PRESET_BIT = 6
_SWITCH_POLL_CHUNK_TICKS = 50_000_000
_SWITCH_POLL_CHUNKS = 60
_CONTROL_PRESET_BROADCAST_SETTLE_CHUNKS = 8


def _require_rust() -> None:
    if not _RUST_OK:
        pytest.fail(f"rust facade not importable: {_RUST_ERROR!r}")


def _require_capture_files() -> None:
    for path in (
        CAPTURE_A_BIN,
        CAPTURE_A_META,
        CAPTURE_B_BIN,
        CAPTURE_B_META,
    ):
        if not path.is_file():
            pytest.skip(f"missing capture fixture: {path}")
    if not V171_CONTROL_HEX.is_file() or not V32_MAIN_HEX.is_file():
        pytest.skip("missing V1.71 / V3.2 firmware artifacts")


def _count_control_routed_frames(rx_bytes: list[int]) -> int:
    return sum(
        1
        for i in range(0, max(0, len(rx_bytes) - 1))
        if rx_bytes[i] in (0xB0, 0xB1)
    )


def _wait_for_main1_control_traffic(chain) -> tuple[list[int], int]:  # type: ignore[no-untyped-def]
    rx_bytes = list(chain.main1_rx_record_since_last_capture())
    control_frames = _count_control_routed_frames(rx_bytes)
    if control_frames:
        return rx_bytes, control_frames

    for _ in range(_CONTROL_PRESET_BROADCAST_SETTLE_CHUNKS):
        chain.step_ticks(_SWITCH_POLL_CHUNK_TICKS)
        rx_bytes.extend(chain.main1_rx_record_since_last_capture())
        control_frames = _count_control_routed_frames(rx_bytes)
        if control_frames:
            break
    return rx_bytes, control_frames


def _load_overlays():
    """Load preset A + B capture overlays from the canonical fixtures.

    Returns ``(overlay_a, overlay_b)`` instances ready for
    ``_apply_capture_overlay`` (used for the in-memory hex overlay) or
    ``chain.patch_core_flash`` (used to seed the chain's preset table
    region directly -- mandatory because the rust ``build_seeded_main_
    flash`` only copies V3.x app bytes up to 0x5600 and leaves the
    preset table region 0x5600..0x5FFF as V2.3 seed values).
    """
    from dlcp_fw.flash.dlcp_main_flash import (
        _load_capture_overlay,
        detect_static_hex_version,
        parse_intel_hex,
        resolve_capture_flash_base,
    )

    hex_mem = parse_intel_hex(str(V32_MAIN_HEX))
    target_version = detect_static_hex_version(hex_mem)
    overlay_a = _load_capture_overlay(
        capture_path=CAPTURE_A_BIN,
        explicit_meta=CAPTURE_A_META,
        name_override=None,
        preset="A",
        flash_base=resolve_capture_flash_base(
            preset="A", target_version=target_version,
        ),
    )
    overlay_b = _load_capture_overlay(
        capture_path=CAPTURE_B_BIN,
        explicit_meta=CAPTURE_B_META,
        name_override=None,
        preset="B",
        flash_base=resolve_capture_flash_base(
            preset="B", target_version=target_version,
        ),
    )
    return overlay_a, overlay_b


def _patch_chain_preset_tables(chain, overlay_a, overlay_b) -> None:  # type: ignore[no-untyped-def]
    """Patch the chain's MAIN0 + MAIN1 program flash with the preset
    A + B capture tables directly.  Required because the rust sim's
    ``build_seeded_main_flash`` only merges v3_app bytes up to
    ``MAIN_APP_PATCH_LIMIT = 0x5600`` (the start of the preset table
    region) -- bytes from 0x5600 onwards are left as V2.3 seed values.

    Without this patching, post-flash cmd 0x43 verifies would read
    V2.3 preset bytes instead of the captures the test expects.
    """
    for core_idx in (1, 2):  # 1=MAIN0, 2=MAIN1
        chain.patch_core_flash(
            core_idx, overlay_a.flash_base, bytes(overlay_a.table),
        )
        chain.patch_core_flash(
            core_idx, overlay_b.flash_base, bytes(overlay_b.table),
        )


def _read_v32_eeprom_identity() -> tuple[int, int, int]:
    """Pull the canonical V3.2 EEPROM identity (major, minor, revision)
    from the parsed V3.2 hex.

    Reading dynamically (instead of hardcoding 0x4F) keeps the test
    robust to canonical V3.2 release rev bumps via
    ``scripts/build_v32_release.py`` (codex MEDIUM vs 4a4b352).
    """
    from dlcp_fw.flash.dlcp_main_flash import (
        detect_static_hex_eeprom_version,
        parse_intel_hex,
    )
    info = detect_static_hex_eeprom_version(parse_intel_hex(str(V32_MAIN_HEX)))
    if info is None:
        raise RuntimeError(
            f"could not detect EEPROM identity in {V32_MAIN_HEX}"
        )
    return (info.major & 0xFF, info.minor & 0xFF, info.revision & 0xFF)


def _post_step_seed_identity_routes_and_settings(chain, identity):  # type: ignore[no-untyped-def]
    """Post-boot seed so the flasher's preflight + route-pick succeed.

    Why post-boot: the V3.2 firmware writes EEPROM[0x80..0x81] during
    boot (V2.3-stock-derived semantics: 0x02->0x80, 0x03->0x81).  A
    pre-boot ``write_main_eeprom_byte`` seed is overwritten before
    ``run_until_connected`` returns.  Codex MEDIUM vs 6545298 caught
    this -- seed AFTER boot so the flasher's identity probe sees the
    intended values.

    ``identity`` is the (major, minor, revision) tuple to write at
    EEPROM[0x80..0x82].  Caller passes the canonical V3.2 hex's
    identity (read via ``_read_v32_eeprom_identity``) so the seed
    survives V3.2 release-rev bumps without the test going stale.

    ROUTE_RAM_BASE (0x60..0x65) = all-L for MAIN0, all-R for MAIN1 so
    ``_resolve_uniform_route_label`` picks MAIN1 when ``--right`` is
    requested.  ROUTE_SOURCE_RAM_BASE (0xA5..0xAA) = all-L for MAIN1
    so the post-flash ``_apply_all_channel_mapping`` has visible work
    to do (post-test asserts these flip to R).

    MAIN1 volume/input are seeded to a non-default user setting so the
    release-flash path proves HID cmd 0x40 preserves user settings
    instead of flushing the firmware defaults (-96 dB, analog 1).
    """
    major, minor, revision = identity
    # V3.2 EEPROM identity (overrides V2.3 seed + boot writes).
    for unit in (0, 1):
        chain.write_main_eeprom_byte(unit, 0x80, major)
        chain.write_main_eeprom_byte(unit, 0x81, minor)
        chain.write_main_eeprom_byte(unit, 0x82, revision)
    # Route RAM disambiguation for --right: MAIN0 all-L, MAIN1 all-R.
    for offset in range(_ROUTE_LEN):
        chain.write_main_reg(0, _ROUTE_RAM_BASE + offset, _ROUTE_VALUE_L)
        chain.write_main_reg(1, _ROUTE_RAM_BASE + offset, _ROUTE_VALUE_R)
    # Source RAM seed: MAIN1 starts as all-L so the post-flash
    # _apply_all_channel_mapping --all-ch R flip is observable in the
    # final assertion (codex LOW vs 6545298 -- otherwise the assertion
    # is pre-satisfied by the picker-disambiguation seed).
    for offset in range(_ROUTE_LEN):
        chain.write_main_reg(
            1, _ROUTE_SOURCE_RAM_BASE + offset, _ROUTE_VALUE_L,
        )
    # User-settings preservation seed.  EEPROM stores volume high..low
    # at 0x00..0x03, while RAM stores low..high from computed/logical
    # base.  -30 dB is FF FF FF E2.
    for offset, value in enumerate(_USER_VOLUME_MINUS_30):
        chain.write_main_eeprom_byte(1, offset, value)
        chain.write_main_reg(1, _COMPUTED_VOLUME_RAM_BASE + 3 - offset, value)
        chain.write_main_reg(1, _LOGICAL_VOLUME_RAM_BASE + 3 - offset, value)
    chain.write_main_eeprom_byte(1, 0x04, _USER_INPUT_COAX_2)
    chain.write_main_reg(1, _INPUT_SELECT_RAM, _USER_INPUT_COAX_2)
    chain.write_main_reg(1, _INPUT_SELECT_MIRROR_RAM, _USER_INPUT_COAX_2)
    chain.write_main_eeprom_byte(1, 0x0E, _USER_SETUP_PROFILE_SENTINEL)
    chain.write_main_reg(1, _SETUP_PROFILE_RAM, _USER_SETUP_PROFILE_SENTINEL)


def _build_overlaid_chain():  # type: ignore[no-untyped-def]
    """Construct the V1.71+2x V3.2 chain with preset A/B tables patched
    into MAIN0+MAIN1 flash via ``patch_core_flash``.

    Two-step pattern:
      1. Build chain from canonical V3.2 hex (no overlay).  The rust
         sim merges V3.x app onto V2.3 seed only up to 0x5600, so
         preset tables 0x5600..0x5FFF are V2.3 stock at this point.
      2. Patch MAIN0+MAIN1 flash directly with the capture tables via
         ``chain.patch_core_flash``.  Done BEFORE
         ``run_until_connected`` so the firmware boots from the
         overlaid image.
    """
    overlay_a, overlay_b = _load_overlays()
    identity = _read_v32_eeprom_identity()
    chain = RustChain.from_v171_v32(
        control_hex_path=str(V171_CONTROL_HEX),
        main_hex_path=str(V32_MAIN_HEX),
    )
    _patch_chain_preset_tables(chain, overlay_a, overlay_b)
    chain.run_until_connected(limit=400)
    chain.step_ticks(50_000_000)  # boot-side preset-load settle
    _post_step_seed_identity_routes_and_settings(chain, identity)
    chain.step_ticks(2_000_000)  # let firmware observe new route bytes
    return chain, overlay_a, overlay_b, identity


def _decode_preset_table_payloads(table: bytes) -> dict[int, bytes]:
    """Decode the logical TAS3108 writes stored in one V3.2 preset table.

    Each regular entry is 24 bytes.  Byte 1 is the TAS3108 subaddress,
    byte 2 is the data length, and bytes 4.. carry the payload.  V3.2
    applies 96 regular entries from logical 0x5600..0x5EFF plus one
    final logical entry at 0x5F00.
    """
    assert len(table) == _PRESET_TABLE_SIZE
    payloads: dict[int, bytes] = {}
    for off in [*range(0, 0x900, 0x18), 0x900]:
        entry = table[off : off + 0x18]
        subaddr = entry[1]
        length = entry[2]
        assert 0 < length < 0x19, (
            f"invalid TAS3108 payload length at table offset "
            f"0x{off:03X}: 0x{length:02X}"
        )
        assert subaddr not in payloads, (
            f"duplicate TAS3108 subaddr 0x{subaddr:02X} in preset table"
        )
        payloads[subaddr] = bytes(entry[4 : 4 + length])
    return payloads


def _assert_tas_payloads_match_overlay(chain, unit: int, overlay, label: str) -> None:  # type: ignore[no-untyped-def]
    expected = _decode_preset_table_payloads(bytes(overlay.table))
    missing: list[int] = []
    mismatches: list[tuple[int, bytes | None, bytes]] = []
    for subaddr, want in expected.items():
        got = chain.read_main_dsp_write_payload(unit, subaddr)
        if got is None:
            missing.append(subaddr)
        elif got != want:
            mismatches.append((subaddr, got, want))

    assert not missing, (
        f"{label} MAIN{unit} never wrote {len(missing)} expected "
        f"TAS3108 preset payload(s): "
        f"{[f'0x{sub:02X}' for sub in missing[:16]]}"
    )
    assert not mismatches, (
        f"{label} MAIN{unit} TAS3108 payload mismatch in "
        f"{len(mismatches)} subaddr(s); first mismatches: "
        f"{[(f'0x{sub:02X}', got.hex() if got is not None else None, want.hex()) for sub, got, want in mismatches[:6]]}"
    )


def _set_control_preset_bit(chain, target: int) -> None:  # type: ignore[no-untyped-def]
    assert target in (0, 1)
    flags = chain.read_reg(_CONTROL_FLAGS_ADDR)
    mask = 1 << _CONTROL_PRESET_BIT
    if target:
        flags |= mask
    else:
        flags &= ~mask
    chain.write_reg(_CONTROL_FLAGS_ADDR, flags & 0xFF)


def _wait_for_preset_convergence(chain, target: int) -> None:  # type: ignore[no-untyped-def]
    assert target in (0, 1)
    want_bit = _ACTIVE_PRESET_MASK if target else 0
    for _ in range(_SWITCH_POLL_CHUNKS):
        chain.step_ticks(_SWITCH_POLL_CHUNK_TICKS)
        if all(
            (chain.read_main_reg(unit, _ACTIVE_FLAGS_ADDR) & _ACTIVE_PRESET_MASK)
            == want_bit
            and chain.read_main_reg(unit, _PRESET_JOB_STATE) == _PRESET_JOB_IDLE
            for unit in (0, 1)
        ):
            return
    state = [
        (
            unit,
            chain.read_main_reg(unit, _ACTIVE_FLAGS_ADDR),
            chain.read_main_reg(unit, _PRESET_JOB_STATE),
        )
        for unit in (0, 1)
    ]
    raise AssertionError(
        f"preset target {target} did not converge; MAIN states={state!r}"
    )


def _switch_preset_via_control(chain, target: int) -> None:  # type: ignore[no-untyped-def]
    _set_control_preset_bit(chain, target)
    _wait_for_preset_convergence(chain, target)


# ---------------------------------------------------------------------------
# Slim integration: argv plumbing
# ---------------------------------------------------------------------------


def test_v32_release_flash_sim_dry_run_passes_argv_through(tmp_path) -> None:
    """``dlcp_v32_release_flash.main(["--right", "--dry-run"])`` parses
    args, builds the forward argv, runs preflight, and exits cleanly
    -- no chain interaction needed at all.  Pins the build_forward_argv
    plumbing for subsequent end-to-end tests."""
    _require_rust()
    _require_capture_files()
    from dlcp_fw.flash.dlcp_v32_release_flash import main

    rc = main(["--right", "--dry-run"])
    assert rc == 0


# ---------------------------------------------------------------------------
# Full integration: streaming + post-flash finalize
# ---------------------------------------------------------------------------


def test_v32_release_flash_sim_full_main_post_flash_state(capsys) -> None:
    """End-to-end integration test.

    1. Build the V1.71+2x V3.2 chain from the canonical V3.2 hex.
    2. Patch MAIN0+MAIN1 flash with preset A/B capture tables (rust
       sim only merges V3.x bytes up to 0x5600, so preset table region
       must be patched directly).
    3. Pre-seed MAIN EEPROM identity + route RAM.
    4. Install the sim hub; run ``dlcp_v32_release_flash.main(["--right"])``.
    5. Verify post-flash state:
       * Preset A flash table at 0x5600..0x5FFF matches the capture.
       * Preset B flash table at 0x4C00..0x55FF matches the capture.
       * Preset A/B EEPROM filename slots match the capture sidecars.
       * Route RAM is uniform R (all 6 channels = 0x01).
       * ≥1 CONTROL-routed frame hit MAIN1 somewhere during the run
         or a bounded post-run settle (sanity precondition: V1.71
         CONTROL is alive).  This does NOT prove preset-broadcast
         xact-gate behavior; the DETERMINISTIC proof that the gate's
         drop path holds when a cmd 0x20 broadcast arrives in a gate
         window lives in Option 2's sibling test.
       * Flasher's identity probe printed the seeded V3.2 identity
         to stdout (proves ``_probe_device_eeprom_version`` actually
         read the seeded bytes vs falling back to a probe-failure
         warning -- closes codex LOW vs 086fd10).
    """
    _require_rust()
    _require_capture_files()

    chain, overlay_a, overlay_b, identity = _build_overlaid_chain()
    hub = make_sim_hub(chain)

    from dlcp_fw.flash.dlcp_v32_release_flash import main

    # Mark MAIN1's RX capture so we can assert CONTROL was alive
    # during the run as a sanity precondition.  This is "CONTROL is
    # transmitting" not "preset broadcast hit the gate window"; the
    # latter is proven by Option 2's deterministic injection test below.
    #
    # Coverage scope (codex LOW vs a2bb70f, deferred-then-investigated
    # in task #150): this wider assertion proves CONTROL traffic reaches
    # MAIN1 while the flasher runs.  The sibling
    # ``test_v32_release_flash_sim_inject_preset_broadcast_during_xact_gate_does_not_clobber``
    # test proves cmd 0x20 gate behavior under injected broadcasts.
    chain.mark_main1_rx_capture_point()
    with install_sim_hub(hub):
        rc = main(["--right"])
    assert rc == 0, "release flasher main() returned non-zero"

    # ---- Verify CONTROL traffic arrives around the run ----
    rx_bytes, control_frames = _wait_for_main1_control_traffic(chain)
    # Chain frames are 3-byte [route, cmd, data] sequences; route
    # 0xB0/0xB1 proves broadcast/addressed CONTROL traffic.  Walk every
    # byte position because we don't know frame alignment relative to
    # capture start.  If the flasher finishes in a quiescent window,
    # advance a bounded settle before failing.
    assert control_frames >= 1, (
        f"V1.71 CONTROL did not send routed traffic to MAIN1 during "
        f"the run or post-run settle (rx_bytes_len={len(rx_bytes)}, "
        f"control_frame_count={control_frames}). CONTROL is dead or the "
        f"sim chain is not advancing correctly."
    )

    # ---- Verify preset A flash table ----
    # NB: the simulated cmd 0x40 stream does NOT patch the chain's
    # running flash (would corrupt the executing firmware) -- the
    # fixture pre-patched the preset tables before boot.  This
    # assertion is therefore a "fixture survives the run" sanity check
    # (codex LOW vs 6545298), not a "flasher streamed bytes into
    # flash" check.  The MEANINGFUL post-flash verification is the
    # EEPROM filename slot below (genuinely written by firmware-side
    # persist after the flasher's cmd 0x03 + force_persist).
    actual_a = bytes(chain.read_core_flash(2, _PRESET_A_FLASH_BASE, _PRESET_TABLE_SIZE))
    assert actual_a == bytes(overlay_a.table), (
        "preset A flash table mismatch after release flash"
    )

    # ---- Verify preset B flash table (same caveat as above) ----
    actual_b = bytes(chain.read_core_flash(2, _PRESET_B_FLASH_BASE, _PRESET_TABLE_SIZE))
    assert actual_b == bytes(overlay_b.table), (
        "preset B flash table mismatch after release flash"
    )

    # ---- Verify preset A EEPROM filename slot ----
    # MEANINGFUL: the firmware ran the persist code path (driven by
    # the flasher's force_persist EP0 trigger) and wrote RAM 0x2C0..
    # 0x2DD to EEPROM 0x60..0x7D.  This assertion fails if persist
    # broke (e.g. xact gate didn't clear, dirty bit didn't latch).
    actual_a_name = bytes(
        chain.read_main_eeprom_byte(1, _PRESET_A_EEPROM_BASE + i)
        for i in range(_FILENAME_LEN)
    )
    assert actual_a_name == bytes(overlay_a.name_slot), (
        f"preset A EEPROM filename mismatch: got {actual_a_name.hex()}, "
        f"expected {overlay_a.name_slot.hex()}"
    )

    # ---- Verify preset B EEPROM filename slot ----
    actual_b_name = bytes(
        chain.read_main_eeprom_byte(1, _PRESET_B_EEPROM_BASE + i)
        for i in range(_FILENAME_LEN)
    )
    assert actual_b_name == bytes(overlay_b.name_slot), (
        f"preset B EEPROM filename mismatch: got {actual_b_name.hex()}, "
        f"expected {overlay_b.name_slot.hex()}"
    )

    # ---- Verify restored active preset and live filename RAM agree ----
    # BUG-PRESET-01: the flasher writes A then B, then restores the
    # originally active preset through the EP0 reapply path.  EEPROM can
    # verify correctly while RAM 0x2C0..0x2DD still holds the last-written
    # B filename unless the reapply path reloads filename RAM for the
    # restored active preset.
    active_flags = chain.read_main_reg(1, _ACTIVE_FLAGS_ADDR)
    assert (active_flags & _ACTIVE_PRESET_MASK) == 0, (
        f"release flash did not restore preset A: active_flags=0x{active_flags:02X}"
    )
    active_name_ram = bytes(
        chain.read_main_reg(1, _FILENAME_RAM_BASE + i) for i in range(_FILENAME_LEN)
    )
    assert active_name_ram == bytes(overlay_a.name_slot), (
        f"active filename RAM mismatch after preset restore: got "
        f"{active_name_ram.hex()}, expected preset A {overlay_a.name_slot.hex()}"
    )
    _assert_tas_payloads_match_overlay(
        chain, 1, overlay_a, "post-release-flash restored preset A"
    )

    # ---- Verify route shadow RAM is uniform R ----
    routes = bytes(
        chain.read_main_reg(1, _ROUTE_RAM_BASE + i) for i in range(_ROUTE_LEN)
    )
    assert routes == bytes([_ROUTE_VALUE_R] * _ROUTE_LEN), (
        f"route shadow mismatch: got {routes.hex()}, expected all R"
    )

    # ---- Verify route SOURCE RAM flipped from L (seed) to R ----
    # MEANINGFUL: ``_post_step_seed_identity_and_routes`` seeded
    # MAIN1[0xA5..0xAA] = all-L; ``_apply_all_channel_mapping`` writes
    # both ROUTE_RAM_BASE and ROUTE_SOURCE_RAM_BASE during the
    # post-flash --all-ch R finalize.  This catches a regression
    # where ``_apply_all_channel_mapping`` skipped or partially
    # applied (codex LOW vs 6545298).
    source_routes = bytes(
        chain.read_main_reg(1, _ROUTE_SOURCE_RAM_BASE + i) for i in range(_ROUTE_LEN)
    )
    assert source_routes == bytes([_ROUTE_VALUE_R] * _ROUTE_LEN), (
        f"route SOURCE RAM not applied by --all-ch R: got "
        f"{source_routes.hex()}, expected all R "
        f"(seed was all-L; flasher must flip to R)"
    )

    # ---- Verify release flash preserves user volume/input/profile settings ----
    # BUG-SETTINGS-01: app cmd 0x40 used by the flasher must only set the
    # bootloader-entry marker, not flush factory defaults into EEPROM.
    post_flash_eeprom_volume = tuple(
        chain.read_main_eeprom_byte(1, offset) for offset in range(4)
    )
    handoff_settings = hub.device_for_unit(1).last_app_to_bootloader_settings
    assert handoff_settings is not None, "sim did not capture cmd 0x40 handoff settings"
    pre_handoff_computed_volume = handoff_settings["computed_volume"]
    assert isinstance(pre_handoff_computed_volume, bytes)
    expected_post_eeprom_volume = tuple(reversed(pre_handoff_computed_volume))
    assert post_flash_eeprom_volume == expected_post_eeprom_volume, (
        f"release flash changed EEPROM volume away from the pre-flash live "
        f"setting: got {post_flash_eeprom_volume!r}, expected "
        f"{expected_post_eeprom_volume!r} from handoff RAM "
        f"{pre_handoff_computed_volume.hex()}"
    )
    assert chain.read_main_eeprom_byte(1, 0x04) == _USER_INPUT_COAX_2
    post_flash_computed_volume = bytes(
        chain.read_main_reg(1, _COMPUTED_VOLUME_RAM_BASE + i) for i in range(4)
    )
    post_flash_logical_volume = bytes(
        chain.read_main_reg(1, _LOGICAL_VOLUME_RAM_BASE + i) for i in range(4)
    )
    assert post_flash_computed_volume == handoff_settings["computed_volume"]
    assert post_flash_logical_volume == handoff_settings["logical_volume"]
    assert chain.read_main_reg(1, _INPUT_SELECT_RAM) == _USER_INPUT_COAX_2
    assert chain.read_main_reg(1, _INPUT_SELECT_MIRROR_RAM) == _USER_INPUT_COAX_2
    assert chain.read_main_eeprom_byte(1, 0x0E) == _USER_SETUP_PROFILE_SENTINEL
    assert chain.read_main_reg(1, _SETUP_PROFILE_RAM) == _USER_SETUP_PROFILE_SENTINEL

    # ---- Verify EEPROM identity reflects V3.2 (post-seed) ----
    # MEANINGFUL: the V3.2 identity bytes survive the run; the
    # flasher's ``_compare_firmware_identities`` saw V3.2 (rather than
    # the V2.3 seed values that the boot path writes if we don't
    # post-step seed).  Codex MEDIUM vs 6545298 caught the silent
    # regression where pre-boot seeds were overwritten by firmware
    # boot writes.
    eeprom_identity = tuple(
        chain.read_main_eeprom_byte(1, 0x80 + i) for i in range(3)
    )
    assert eeprom_identity == identity, (
        f"V3.2 EEPROM identity drifted during run: got "
        f"{eeprom_identity!r}, expected {identity!r}"
    )

    # ---- Verify flasher's identity probe rendered the seeded values ----
    # Closes codex LOW vs 086fd10: the seed-survival assertion above
    # proves the bytes are still in EEPROM at end-of-test, but doesn't
    # prove the FLASHER's ``_probe_device_eeprom_version`` actually
    # read them during its info-snapshot phase.  If the probe path
    # broke (returned ``None`` and was downgraded to a "EEPROM version
    # probe failed" warning), the seed-survival assertion would still
    # pass.  We check stdout for the rendered ``revision: 0x{rev:02X}
    # (EEPROM {major}.{minor})`` line that ``_print_device_snapshot``
    # emits -- proves the probe ran AND succeeded AND saw the seeded
    # bytes.
    captured = capsys.readouterr()
    expected_revision_line = (
        f"revision: 0x{identity[2]:02X} (EEPROM {identity[0]}.{identity[1]})"
    )
    assert expected_revision_line in captured.out, (
        f"flasher did not print the seeded V3.2 identity "
        f"(expected substring: {expected_revision_line!r}).  Either "
        f"the probe failed and was downgraded to a warning, or the "
        f"identity bytes drifted between seed and probe.\n\n"
        f"--- captured stdout ---\n{captured.out}\n--- end ---"
    )


@pytest.mark.slow
def test_v32_lx521_a_b_payloads_reach_each_main_tas3108() -> None:
    """The release captures must reach the simulated TAS3108 as exact
    logical payload writes, not merely exist in flash or leave both
    MAINs equal.

    This catches the release-class failure where both MAINs can agree
    on the wrong/empty/thin DSP state.  The TAS3108 byte register file
    is lossy for 20-byte biquad writes, so the assertion uses the
    completed-write payload log exposed by the Rust model.
    """
    _require_rust()
    _require_capture_files()

    chain, overlay_a, overlay_b, _ = _build_overlaid_chain()
    payloads_a = _decode_preset_table_payloads(bytes(overlay_a.table))
    payloads_b = _decode_preset_table_payloads(bytes(overlay_b.table))
    differing = {
        subaddr
        for subaddr in payloads_a
        if payloads_a[subaddr] != payloads_b[subaddr]
    }
    assert {0x37, 0x38, 0x73, 0x77, 0x78, 0x82, 0x86, 0x87}.issubset(
        differing
    ), (
        f"LX521 A/B capture fixture no longer differs in the expected "
        f"biquad-heavy subaddresses; differing={sorted(differing)!r}"
    )

    for unit in (0, 1):
        _assert_tas_payloads_match_overlay(chain, unit, overlay_a, "boot preset A")
        chain.reset_main_dsp_write_log(unit)

    _switch_preset_via_control(chain, 1)

    for unit in (0, 1):
        _assert_tas_payloads_match_overlay(chain, unit, overlay_b, "switched preset B")


# ---------------------------------------------------------------------------
# Race-stress test: actively inject CONTROL preset broadcast at the worst-
# case timing (between cmd 0x03 WRITE and force_persist completion) and
# verify the xact gate (filename_dirty_flags bit 6) drops the broadcast
# without clobbering the host-written RAM filename.
# ---------------------------------------------------------------------------


_RX_RING_BASE = 0x0200
_RX_RING_SIZE = 0xC0
_RX_RING_RD = 0x0C6
_RX_RING_WR = 0x0C7

# preset_job state-machine addresses (V3.2 asm:153-154).  We inspect
# these to prove the xact gate dropped at preset_select_handler entry
# (asm:9532) without storing the target -- not just that the preset
# bit hadn't yet toggled (which would also be true if the gate failed
# but the HOLDING timer hadn't fired).  Codex MEDIUM vs a2bb70f.
_PRESET_JOB_STATE_ADDR = 0x2DE
_PRESET_JOB_TARGET_ADDR = 0x2DF
_PRESET_JOB_STATE_IDLE = 0x00


def _inject_main1_chain_frame(chain, frame: tuple[int, int, int]) -> None:  # type: ignore[no-untyped-def]
    """Inject a 3-byte chain frame directly into MAIN1's RX ring at
    physical 0x0200..0x02BF (V3.x convention; rd at 0x0C6, wr at
    0x0C7).  Mirror of ``inject_main_frames_fifo`` but targets MAIN1
    instead of MAIN0 -- used to deterministically place a CONTROL
    preset broadcast in MAIN1's parser queue, bypassing the
    CONTROL->MAIN0->MAIN1 forward latency.
    """
    rd = chain.read_main_reg(1, _RX_RING_RD) % _RX_RING_SIZE
    wr = chain.read_main_reg(1, _RX_RING_WR) % _RX_RING_SIZE
    used = (wr + _RX_RING_SIZE - rd) % _RX_RING_SIZE
    free = _RX_RING_SIZE - 1 - used  # 1-byte free-slot accounting
    if free < len(frame):
        raise RuntimeError(
            f"MAIN1 RX ring full: free={free}, frame={len(frame)}"
        )
    for byte in frame:
        chain.write_main_reg(1, _RX_RING_BASE + wr, byte & 0xFF)
        wr = (wr + 1) % _RX_RING_SIZE
    chain.write_main_reg(1, _RX_RING_WR, wr)


def test_v32_release_flash_sim_inject_preset_broadcast_during_xact_gate_does_not_clobber() -> None:
    """Race-stress: inject a CONTROL preset broadcast at the worst-
    case timing -- between the flasher's cmd 0x03 WRITE filename and
    force_persist completion (gate bit 6 set + RAM 0x2C0..0x2DD
    populated with host bytes).  Verify the xact gate drops the
    injected broadcast (RAM unchanged, preset bit unchanged, gate
    still set).  Then complete force_persist and verify EEPROM gets
    the host-written filename, not the broadcast's would-be clobber.

    This is the DETERMINISTIC proof of gate-drop semantics under a
    cmd 0x20 broadcast in a gate-active window.  The sibling full-
    main test only proves CONTROL is alive during the run -- not
    that a natural broadcast hit a gate window (per task #150
    investigation, per-preset gate windows are ~ 125 ms sim time
    vs V1.71 CONTROL's ~ 6 s preset broadcast cadence, so natural
    overlap is reliably empty).  Hence this Option 2 test exists
    to actively force the worst-case timing.
    """
    _require_rust()
    _require_capture_files()

    chain, _, _, _ = _build_overlaid_chain()
    hub = make_sim_hub(chain)

    from dlcp_fw.flash.dlcp_main_flash import (
        _force_active_filename_persist,
    )

    path = hub.device_for_unit(1).path

    with install_sim_hub(hub):
        hid_dev = hub.open_hid_path(path)

        # Determine current preset (firmware may have booted into A or B
        # depending on EEPROM state).
        active_flags_initial = chain.read_main_reg(1, 0x05E)
        current_preset_b = bool(active_flags_initial & 0x04)
        opposite_preset_data = 0 if current_preset_b else 1
        current_preset_letter = "B" if current_preset_b else "A"
        current_eeprom_base = (
            _PRESET_B_EEPROM_BASE if current_preset_b else _PRESET_A_EEPROM_BASE
        )

        # Snapshot preset_job state-machine BEFORE the cmd 0x03 +
        # injection so the post-injection assertion can prove these
        # didn't move (i.e. the broadcast was dropped at gate entry,
        # not merely "still in HOLDING but timer hasn't fired").
        preset_job_state_initial = chain.read_main_reg(1, _PRESET_JOB_STATE_ADDR)
        preset_job_target_initial = chain.read_main_reg(1, _PRESET_JOB_TARGET_ADDR)
        assert preset_job_state_initial == _PRESET_JOB_STATE_IDLE, (
            f"preset_job_state not IDLE at test start: "
            f"0x{preset_job_state_initial:02X}"
        )

        # ---- Step 1: cmd 0x03 WRITE filename ----
        # Per V3.2 firmware (asm:355-374), 0x00 in payload bytes 2..0x1F
        # maps to 0xFF in RAM.  Host's _name_slot_to_cmd03_payload does
        # the inverse (0x00/0xFF in name slot -> 0x00 in payload), so
        # name bytes are verbatim and trailing 0x00 in payload becomes
        # 0xFF in RAM.
        host_name_bytes = b"RACE-CHECK-NAME"
        payload = bytearray(64)
        payload[0] = 0x03
        payload[1] = 0x09  # WRITE subcmd
        payload[2 : 2 + len(host_name_bytes)] = host_name_bytes
        n = hid_dev.write(b"\x00" + bytes(payload))
        assert n == 65
        resp = hid_dev.read(64, 1000)
        assert len(resp) == 64
        assert resp[0] == 0x03 and resp[1] == 0x09

        # Verify cmd 0x03 actually populated RAM and set bits 5+6.
        flags_after_write = chain.read_main_reg(1, 0x0BD)
        assert flags_after_write & 0x40, (
            f"bit 6 (xact pending) not set after cmd 0x03 WRITE: "
            f"0x{flags_after_write:02X}"
        )
        assert flags_after_write & 0x20, (
            f"bit 5 (filename dirty) not set after cmd 0x03 WRITE: "
            f"0x{flags_after_write:02X}"
        )
        for i, b in enumerate(host_name_bytes):
            ram = chain.read_main_reg(1, 0x2C0 + i)
            assert ram == b, (
                f"RAM filename[{i}]=0x{ram:02X}, expected 0x{b:02X} "
                f"after cmd 0x03 WRITE"
            )

        # ---- Step 2: Inject CONTROL preset broadcast for OPPOSITE preset ----
        # The firmware's preset_select_handler (asm:9525) reads
        # filename_dirty_flags.6 first; if set, it BRA's to
        # preset_select_handler_done without storing the target or
        # toggling preset.  Without the gate, the request would call
        # preset_load_filename which clobbers RAM 0x2C0..0x2DD with
        # the incoming preset's stored EEPROM filename -- corrupting
        # the host's just-written bytes.
        _inject_main1_chain_frame(chain, (0xB0, 0x20, opposite_preset_data))
        # Step the chain so MAIN1's parser drains the RX ring.  The
        # parser runs every main-loop iteration (~ 200 Tcy); 5 M ticks
        # is ~ 100 ms sim time, plenty for the parser to dequeue and
        # dispatch.
        chain.step_ticks(5_000_000)

        # ---- Step 3: Verify gate held under the injected broadcast ----
        for i, b in enumerate(host_name_bytes):
            ram = chain.read_main_reg(1, 0x2C0 + i)
            assert ram == b, (
                f"RAM filename[{i}] CLOBBERED by injected broadcast: "
                f"got 0x{ram:02X}, expected 0x{b:02X}.  "
                f"xact gate failed -- preset_select_handler did NOT "
                f"drop the broadcast under bit 6 set."
            )
        # Trailing padding bytes should remain 0xFF (the firmware-side
        # 0x00 -> 0xFF mapping should have produced these during cmd
        # 0x03 WRITE).
        for i in range(len(host_name_bytes), _FILENAME_LEN):
            ram = chain.read_main_reg(1, 0x2C0 + i)
            assert ram == 0xFF, (
                f"RAM filename padding[{i}]=0x{ram:02X}, expected 0xFF"
            )
        flags_after_inject = chain.read_main_reg(1, 0x0BD)
        assert flags_after_inject & 0x40, (
            f"bit 6 cleared by injected broadcast: "
            f"0x{flags_after_inject:02X}"
        )
        active_flags_after_inject = chain.read_main_reg(1, 0x05E)
        assert (active_flags_after_inject & 0x04) == (
            active_flags_initial & 0x04
        ), (
            f"preset bit toggled by injected broadcast despite gate: "
            f"before=0x{active_flags_initial:02X}, "
            f"after=0x{active_flags_after_inject:02X}"
        )

        # ---- Step 3b: Verify the gate dropped at TOP-OF-HANDLER ----
        # Without this, "preset bit unchanged" would also hold if the
        # gate failed but the HOLDING timer (~150 ms) hadn't fired
        # yet -- only 100 ms elapsed in step 2.  Reading
        # preset_job_state directly proves the handler returned at
        # asm:9532-9533 without ever reaching the state-machine entry
        # at asm:9547+.  Codex MEDIUM vs a2bb70f.
        preset_job_state_after = chain.read_main_reg(
            1, _PRESET_JOB_STATE_ADDR,
        )
        preset_job_target_after = chain.read_main_reg(
            1, _PRESET_JOB_TARGET_ADDR,
        )
        assert preset_job_state_after == _PRESET_JOB_STATE_IDLE, (
            f"preset_job_state moved to 0x{preset_job_state_after:02X} "
            f"(not IDLE) after injected broadcast: gate did NOT drop "
            f"at preset_select_handler entry -- handler reached the "
            f"PENDING state-machine entry path despite bit 6 set."
        )
        assert preset_job_target_after == preset_job_target_initial, (
            f"preset_job_target was clobbered by injected broadcast "
            f"despite gate: before=0x{preset_job_target_initial:02X}, "
            f"after=0x{preset_job_target_after:02X}.  Handler reached "
            f"asm:9534-9537 (target store) despite bit 6 set."
        )

        # ---- Step 4: force_persist clears the gate + persists RAM->EEPROM ----
        forced = _force_active_filename_persist(
            vid=SimUsbHub.DEFAULT_VID,
            pid=SimUsbHub.DEFAULT_PID,
            path=path,
            timeout_s=2.0,
            poll_s=0.005,
        )
        assert forced, "force_persist returned False (no work to do)"
        flags_after_persist = chain.read_main_reg(1, 0x0BD)
        assert (flags_after_persist & 0x60) == 0, (
            f"force_persist did not clear bits 5+6: "
            f"0x{flags_after_persist:02X}"
        )

    # ---- Step 5: Verify EEPROM matches host's bytes (NOT clobber) ----
    # preset_persist_filename writes RAM 0x2C0..0x2DD to EEPROM at
    # the CURRENT preset's slot (asm:9558 selects A vs B by
    # active_flags.bit2).  We proved bit 2 unchanged above, so the
    # slot we read here matches the slot the firmware wrote to.
    for i, b in enumerate(host_name_bytes):
        eb = chain.read_main_eeprom_byte(1, current_eeprom_base + i)
        assert eb == b, (
            f"EEPROM[{current_eeprom_base + i:#04x}]=0x{eb:02X}, expected "
            f"0x{b:02X} (host's cmd 0x03 byte; race-stress preset "
            f"{current_preset_letter})"
        )
    for i in range(len(host_name_bytes), _FILENAME_LEN):
        eb = chain.read_main_eeprom_byte(1, current_eeprom_base + i)
        assert eb == 0xFF, (
            f"EEPROM[{current_eeprom_base + i:#04x}]=0x{eb:02X}, expected "
            f"0xFF (padding)"
        )
