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


def _post_step_seed_identity_and_routes(chain) -> None:  # type: ignore[no-untyped-def]
    """Post-boot seed so the flasher's preflight + route-pick succeed.

    Why post-boot: the V3.2 firmware writes EEPROM[0x80..0x81] during
    boot (V2.3-stock-derived semantics: 0x02->0x80, 0x03->0x81).  A
    pre-boot ``write_main_eeprom_byte`` seed is overwritten before
    ``run_until_connected`` returns.  Codex MEDIUM vs 6545298 caught
    this -- seed AFTER boot so the flasher's identity probe sees the
    intended values.

    EEPROM[0x80..0x82] = (3, 2, rev): V3.2 identity, so the flasher's
    ``_compare_firmware_identities`` doesn't emit "downgrade" warnings.

    ROUTE_RAM_BASE (0x60..0x65) = all-L for MAIN0, all-R for MAIN1 so
    ``_resolve_uniform_route_label`` picks MAIN1 when ``--right`` is
    requested.  ROUTE_SOURCE_RAM_BASE (0xA5..0xAA) = all-L for MAIN1
    so the post-flash ``_apply_all_channel_mapping`` has visible work
    to do (post-test asserts these flip to R).
    """
    # V3.2 EEPROM identity (overrides V2.3 seed + boot writes).
    for unit in (0, 1):
        chain.write_main_eeprom_byte(unit, 0x80, 3)
        chain.write_main_eeprom_byte(unit, 0x81, 2)
        chain.write_main_eeprom_byte(unit, 0x82, 0x4F)
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
    chain = RustChain.from_v171_v32(
        control_hex_path=str(V171_CONTROL_HEX),
        main_hex_path=str(V32_MAIN_HEX),
    )
    _patch_chain_preset_tables(chain, overlay_a, overlay_b)
    chain.run_until_connected(limit=400)
    chain.step_ticks(50_000_000)  # boot-side preset-load settle
    _post_step_seed_identity_and_routes(chain)
    chain.step_ticks(2_000_000)  # let firmware observe new route bytes
    return chain, overlay_a, overlay_b


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


def test_v32_release_flash_sim_full_main_post_flash_state() -> None:
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
    """
    _require_rust()
    _require_capture_files()

    chain, overlay_a, overlay_b = _build_overlaid_chain()
    hub = make_sim_hub(chain)

    from dlcp_fw.flash.dlcp_v32_release_flash import main

    with install_sim_hub(hub):
        rc = main(["--right"])
    assert rc == 0, "release flasher main() returned non-zero"

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

    # ---- Verify EEPROM identity reflects V3.2 (post-seed) ----
    # MEANINGFUL: the V3.2 identity bytes survive the run; the
    # flasher's ``_compare_firmware_identities`` saw V3.2 (rather than
    # the V2.3 seed values that the boot path writes if we don't
    # post-step seed).  Codex MEDIUM vs 6545298 caught the silent
    # regression where pre-boot seeds were overwritten by firmware
    # boot writes.
    eeprom_identity = bytes(
        chain.read_main_eeprom_byte(1, 0x80 + i) for i in range(3)
    )
    assert eeprom_identity == bytes([3, 2, 0x4F]), (
        f"V3.2 EEPROM identity drifted during run: got "
        f"{eeprom_identity.hex()}, expected 03 02 4F"
    )
