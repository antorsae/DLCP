from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import STOCK_CONTROL_HEX_V14
from dlcp_fw.flash.dlcp_control_flash import (
    CONTROL_BOOT_START,
    PreflightError,
    bootloader_mismatch_addresses,
    main,
    parse_intel_hex,
    run_preflight,
)


def _stock_control_v14() -> Path:
    return STOCK_CONTROL_HEX_V14


def test_preflight_bootloader_match(patched_control_hex: Path) -> None:
    candidate = parse_intel_hex(str(patched_control_hex))
    reference = parse_intel_hex(str(_stock_control_v14()))
    preflight = run_preflight(
        hex_mem=candidate,
        bootloader_ref_mem=reference,
        require_bootloader_match=True,
    )
    assert preflight["bootloader_match"] is True


def test_preflight_rejects_bootloader_drift(patched_control_hex: Path) -> None:
    candidate = parse_intel_hex(str(patched_control_hex))
    reference = parse_intel_hex(str(_stock_control_v14()))
    candidate_mut = dict(candidate)
    candidate_mut[CONTROL_BOOT_START] = (candidate_mut.get(CONTROL_BOOT_START, 0xFF) ^ 0x01) & 0xFF

    with pytest.raises(PreflightError, match="bootloader bytes differ from reference"):
        run_preflight(
            hex_mem=candidate_mut,
            bootloader_ref_mem=reference,
            require_bootloader_match=True,
        )


def test_bootloader_mismatch_addresses_reports_exact_site(patched_control_hex: Path) -> None:
    candidate = parse_intel_hex(str(patched_control_hex))
    reference = parse_intel_hex(str(_stock_control_v14()))
    candidate_mut = dict(candidate)
    target = CONTROL_BOOT_START + 0x37
    candidate_mut[target] = (candidate_mut.get(target, 0xFF) ^ 0x80) & 0xFF

    mismatches = bootloader_mismatch_addresses(candidate_mut, reference)
    assert target in mismatches


def test_preflight_without_bootloader_check_allows_no_reference(patched_control_hex: Path) -> None:
    candidate = parse_intel_hex(str(patched_control_hex))
    preflight = run_preflight(
        hex_mem=candidate,
        bootloader_ref_mem=None,
        require_bootloader_match=False,
    )
    assert preflight["payload_len"] > 0


def test_cli_blocks_unsafe_flags_without_force(patched_control_hex: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--hex", str(patched_control_hex), "--preflight-only", "--no-verify"])
    assert exc.value.code == 2


def test_cli_allows_unsafe_when_explicitly_forced(patched_control_hex: Path) -> None:
    rc = main(["--hex", str(patched_control_hex), "--preflight-only", "--no-verify", "--force-unsafe"])
    assert rc == 0
