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


def _seed_mains_with_v32_identity_and_routes(chain) -> None:  # type: ignore[no-untyped-def]
    """Pre-step seed so the flasher's preflight + route-pick succeed.

    EEPROM[0x80..0x82] = (3, 2, rev): V3.2 identity, so the flasher's
    ``_compare_firmware_identities`` doesn't emit downgrade warnings
    (would still proceed -- this is just cosmetic).

    ROUTE_RAM_BASE for MAIN0 = all-L (0x00), MAIN1 = all-R (0x01) so
    ``_resolve_uniform_route_label`` picks MAIN1 when ``--right`` is
    requested.

    The route bytes are also seeded into MAIN0/MAIN1 EEPROM via the
    firmware's normal route-shadow path (route_dirty bit cleared after
    boot) -- but here we just poke the RAM bytes directly so the
    EP0-side ``_probe_ep0_app_ram`` reads the expected labels.
    """
    # V3.2 EEPROM identity (overrides V2.3 seed).
    chain.write_main_eeprom_byte(0, 0x80, 3)
    chain.write_main_eeprom_byte(0, 0x81, 2)
    chain.write_main_eeprom_byte(0, 0x82, 0x4F)
    chain.write_main_eeprom_byte(1, 0x80, 3)
    chain.write_main_eeprom_byte(1, 0x81, 2)
    chain.write_main_eeprom_byte(1, 0x82, 0x4F)


def _post_step_seed_routes(chain) -> None:  # type: ignore[no-untyped-def]
    """After ``run_until_connected`` + a settle step, poke the route
    RAM bytes so route-label disambiguation works.

    Done after boot so the firmware's own EEPROM->RAM copy doesn't
    overwrite our pokes."""
    for offset in range(_ROUTE_LEN):
        chain.write_main_reg(0, _ROUTE_RAM_BASE + offset, _ROUTE_VALUE_L)
        chain.write_main_reg(1, _ROUTE_RAM_BASE + offset, _ROUTE_VALUE_R)


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
    _seed_mains_with_v32_identity_and_routes(chain)
    chain.run_until_connected(limit=400)
    chain.step_ticks(50_000_000)  # boot-side preset-load settle
    _post_step_seed_routes(chain)
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
    actual_a = bytes(chain.read_core_flash(2, _PRESET_A_FLASH_BASE, _PRESET_TABLE_SIZE))
    assert actual_a == bytes(overlay_a.table), (
        "preset A flash table mismatch after release flash"
    )

    # ---- Verify preset B flash table ----
    actual_b = bytes(chain.read_core_flash(2, _PRESET_B_FLASH_BASE, _PRESET_TABLE_SIZE))
    assert actual_b == bytes(overlay_b.table), (
        "preset B flash table mismatch after release flash"
    )

    # ---- Verify preset A EEPROM filename slot ----
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

    # ---- Verify route mapping is uniform R ----
    routes = bytes(
        chain.read_main_reg(1, _ROUTE_RAM_BASE + i) for i in range(_ROUTE_LEN)
    )
    assert routes == bytes([_ROUTE_VALUE_R] * _ROUTE_LEN), (
        f"route mapping mismatch: got {routes.hex()}, expected all R"
    )
