from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import STOCK_CONTROL_HEX_V14, V171_CONTROL_HEX
from dlcp_fw.flash.dlcp_control_flash import (
    CONTROL_BOOT_START,
    CONTROL_PROG_END_EXCL,
    CONTROL_RELEASE_MAGIC,
    CONTROL_RELEASE_METADATA_ADDR,
    HidDeviceInfo,
    PreflightError,
    _pick_device,
    build_control_stream,
    bootloader_mismatch_addresses,
    detect_static_hex_control_release_info,
    main,
    parse_intel_hex,
    run_preflight,
)
from dlcp_fw.patch.build_v171_release import build_v171_release


# All tests in this module are backend-agnostic (static source/hex
# analysis, flash-tool CLI plumbing, semantic-guard regex matchers).
# Mark the whole module dual_supported (legacy informational
# marker; see tests/sim/conftest.py for the post-PF.4 inert
# semantics).
pytestmark = pytest.mark.dual_supported


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


def test_detect_static_hex_control_release_info_v171() -> None:
    release = detect_static_hex_control_release_info(parse_intel_hex(str(V171_CONTROL_HEX)))
    assert release is not None
    assert (release.major, release.minor, release.sub) == (0x01, 0x07, 0x31)
    assert release.revision is not None
    assert release.revision >= 0x01


def test_v171_release_metadata_is_within_flashable_app_window() -> None:
    assert CONTROL_RELEASE_METADATA_ADDR >= 0x0040
    assert CONTROL_RELEASE_METADATA_ADDR + 12 <= CONTROL_PROG_END_EXCL


def test_build_control_stream_preserves_release_metadata_bytes() -> None:
    candidate = parse_intel_hex(str(V171_CONTROL_HEX))
    stream = build_control_stream(candidate)
    offset = CONTROL_RELEASE_METADATA_ADDR
    assert stream[offset : offset + len(CONTROL_RELEASE_MAGIC)] == CONTROL_RELEASE_MAGIC
    assert stream[offset + 8 : offset + 11] == bytes([0x01, 0x07, 0x31])


def test_preflight_reports_target_release_and_compare_limitation(capsys) -> None:
    rc = main(["--hex", str(V171_CONTROL_HEX), "--preflight-only"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "target release: V1.71 / rev 0x" in out
    assert "live CONTROL version/revision probe is unavailable" in out


def test_build_v171_release_rolls_back_source_and_hex_on_assemble_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asm_path = tmp_path / "dlcp_control_v171.asm"
    original_text = (
        "control_release_metadata:\n"
        "        db      0x01, 0x07, 0x31, 0x02\n"
    )
    asm_path.write_text(original_text, encoding="utf-8")
    output_hex = tmp_path / "DLCP_Control_V1.71.hex"
    output_hex.write_text(":00000001FF\n", encoding="ascii")

    def _boom(*args, **kwargs):
        raise RuntimeError("gpasm boom")

    monkeypatch.setattr("dlcp_fw.patch.build_v171_release.assemble_v17", _boom)

    with pytest.raises(RuntimeError, match="gpasm boom"):
        build_v171_release(asm_path=asm_path, output_hex=output_hex)

    assert asm_path.read_text(encoding="utf-8") == original_text
    assert output_hex.read_text(encoding="ascii") == ":00000001FF\n"


def test_pick_device_rejects_ambiguous_auto_select(monkeypatch) -> None:
    dev_a = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=b"path-a",
        manufacturer_string="Hypex",
        product_string="DLCP",
        serial_number="A",
    )
    dev_b = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=b"path-b",
        manufacturer_string="Hypex",
        product_string="DLCP",
        serial_number="B",
    )
    monkeypatch.setattr("dlcp_fw.flash.dlcp_control_flash.enumerate_devices", lambda vid, pid: [dev_a, dev_b])

    with pytest.raises(RuntimeError, match="multiple HID devices match"):
        _pick_device(0x04D8, 0xFF89, None)

    assert _pick_device(0x04D8, 0xFF89, b"path-b") == dev_b
