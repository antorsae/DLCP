from __future__ import annotations

import importlib

import pytest

pytestmark = pytest.mark.dual_supported


def _reload(module_name: str):
    return importlib.reload(importlib.import_module(module_name))


def test_v31_paths_keep_canonical_constants_under_env_override(monkeypatch) -> None:
    monkeypatch.setenv("DLCP_FW_V31_MAIN_ASM", "tmp/override_v31.asm")
    monkeypatch.setenv("DLCP_FW_V31_MAIN_HEX", "tmp/override_v31.hex")

    paths = _reload("dlcp_fw.paths")

    assert paths.V31_MAIN_ASM == (paths.PROJECT_ROOT / "tmp" / "override_v31.asm").resolve()
    assert paths.V31_MAIN_HEX == (paths.PROJECT_ROOT / "tmp" / "override_v31.hex").resolve()
    assert paths.V31_MAIN_ASM_CANONICAL == (
        paths.PROJECT_ROOT / "src" / "dlcp_fw" / "asm" / "dlcp_main_v31.asm"
    )
    assert paths.V31_MAIN_HEX_CANONICAL == (
        paths.FIRMWARE_PATCHED_DIR / "DLCP_Firmware_V3.1.hex"
    )
    assert paths.V31_MAIN_ASM != paths.V31_MAIN_ASM_CANONICAL
    assert paths.V31_MAIN_HEX != paths.V31_MAIN_HEX_CANONICAL


def test_v31_cmd07_guard_builder_is_idempotent_on_current_source() -> None:
    mod = _reload("dlcp_fw.patch.build_v31_cmd07_stock_guard_usb_safe")
    text = mod.SOURCE_ASM.read_text(encoding="utf-8", errors="replace")

    assert mod._rewrite_source(text) == text


def test_v31_diag_coeff_builder_is_idempotent_on_current_source() -> None:
    mod = _reload("dlcp_fw.patch.build_v31_diag_coeff_stock")
    text = mod.SOURCE_ASM.read_text(encoding="utf-8", errors="replace")

    assert mod._rewrite_source(text) == text


def test_v31_diag_coeff_structural_detector_distinguishes_old_from_new() -> None:
    """Pin the structural detector contract: ``_is_already_stock_coeff_write``
    must classify the current canonical V3.1 source (post-rcall optimizations)
    as "already stock" AND classify the legacy bounded ``_OLD_COEFF_BLOCK``
    shape as NOT stock.  Without this pinning, a future refactor that broadens
    the predicate (e.g. drops the ``wait_sen_bounded not in body`` clause)
    would silently regress the legacy rewrite path while the
    current-source idempotence test stayed green (codex LOW vs cbe2b66).

    Plus three synthetic per-clause checks (codex LOW vs 05323b9): each
    clause of the triple-check predicate
    (``coeff_write_wait_sen_stock:`` present + ``coeff_write_pen_stock:``
    present + ``wait_sen_bounded`` absent) must individually be load-bearing.
    Hand-crafted inputs exercise the case where exactly one clause is
    flipped vs the canonical-stock shape, and the detector must reject."""
    mod = _reload("dlcp_fw.patch.build_v31_diag_coeff_stock")
    current_text = mod.SOURCE_ASM.read_text(encoding="utf-8", errors="replace")

    assert mod._is_already_stock_coeff_write(current_text), (
        "current canonical V3.1 source must be detected as already-stock"
    )
    assert not mod._is_already_stock_coeff_write(mod._OLD_COEFF_BLOCK), (
        "legacy bounded coeff-write block must NOT match the stock detector "
        "(otherwise the rewrite from OLD -> NEW would silently no-op)"
    )

    # Synthetic shapes that flip exactly one clause vs the stock body.
    # Each must be REJECTED by the detector or the corresponding clause is
    # not load-bearing.
    _STOCK_SKELETON = (
        "i2c_tas3108_coeff_write:\n"
        "    rcall       i2c_wait_bus_idle\n"
        "    bsf         SSPCON2, 0, ACCESS\n"
        "coeff_write_wait_sen_stock:\n"
        "    btfsc       SSPCON2, 0, ACCESS\n"
        "    bra         coeff_write_wait_sen_stock\n"
        "    bsf         SSPCON2, 2, ACCESS\n"
        "coeff_write_pen_stock:\n"
        "    btfss       SSPCON2, 2, ACCESS\n"
        "    bra         coeff_write_pen_done\n"
        "    bra         coeff_write_pen_stock\n"
        "coeff_write_pen_done:\n"
        "    return      0\n"
        "\n"
    )
    assert mod._is_already_stock_coeff_write(_STOCK_SKELETON), (
        "stock skeleton (control case) must match"
    )

    no_start = _STOCK_SKELETON.replace("coeff_write_wait_sen_stock:", "missing_label_a:")
    assert not mod._is_already_stock_coeff_write(no_start), (
        "skeleton without coeff_write_wait_sen_stock: must be rejected; "
        "START-wait-label clause is not load-bearing"
    )
    no_stop = _STOCK_SKELETON.replace("coeff_write_pen_stock:", "missing_label_b:")
    assert not mod._is_already_stock_coeff_write(no_stop), (
        "skeleton without coeff_write_pen_stock: must be rejected; "
        "STOP-wait-label clause is not load-bearing"
    )
    with_bounded = _STOCK_SKELETON.replace(
        "    rcall       i2c_wait_bus_idle\n",
        "    rcall       i2c_wait_bus_idle\n    rcall       wait_sen_bounded\n",
    )
    assert not mod._is_already_stock_coeff_write(with_bounded), (
        "skeleton WITH wait_sen_bounded inside the function body must be "
        "rejected; bounded-wait-absence clause is not load-bearing"
    )


def test_v31_release_builders_use_canonical_inputs(monkeypatch) -> None:
    monkeypatch.setenv("DLCP_FW_V31_MAIN_ASM", "tmp/override_v31.asm")
    monkeypatch.setenv("DLCP_FW_V31_MAIN_HEX", "tmp/override_v31.hex")

    paths = _reload("dlcp_fw.paths")
    modules = [
        "dlcp_fw.patch.build_v31_cmd07_stock_guard_usb_safe",
        "dlcp_fw.patch.build_v31_diag_coeff_stock",
        "dlcp_fw.patch.build_v31_diag_memread_usb_safe",
        "dlcp_fw.patch.build_v31_diag_no_flash_remap_usb_safe",
        "dlcp_fw.patch.build_v31_diag_stock_bf",
        "dlcp_fw.patch.build_v31_diag_stock_bf_reg1f",
        "dlcp_fw.patch.build_v31_diag_stock_i2c_byte_tx",
        "dlcp_fw.patch.build_v31_diag_v27_pen_hook",
        "dlcp_fw.patch.build_v31_usb_safe",
    ]

    for module_name in modules:
        mod = _reload(module_name)
        if hasattr(mod, "SOURCE_ASM"):
            assert mod.SOURCE_ASM == paths.V31_MAIN_ASM_CANONICAL
        if hasattr(mod, "SOURCE_HEX"):
            assert mod.SOURCE_HEX == paths.V31_MAIN_HEX_CANONICAL


def test_legacy_usb_safe_builders_write_to_ignored_artifacts_dir() -> None:
    paths = _reload("dlcp_fw.paths")
    builders = [
        _reload("dlcp_fw.patch.build_v30_usb_safe"),
        _reload("dlcp_fw.patch.build_v31_usb_safe"),
    ]

    for mod in builders:
        assert mod.OUT_HEX.parent == paths.ARTIFACTS_DIR / "reanalysis" / "usb_safe"
        assert mod.OUT_HEX.parent != paths.FIRMWARE_PATCHED_DIR


def test_v31_nop_builder_remains_override_aware(monkeypatch) -> None:
    monkeypatch.setenv("DLCP_FW_V31_MAIN_ASM", "tmp/override_v31.asm")

    paths = _reload("dlcp_fw.paths")
    mod = _reload("dlcp_fw.patch.build_v31_nop_variants")

    assert mod.V31_MAIN_ASM == paths.V31_MAIN_ASM
    assert mod.V31_MAIN_ASM != paths.V31_MAIN_ASM_CANONICAL
