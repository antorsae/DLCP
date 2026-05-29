"""V1.72/V3.3 release-builder regression tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.patch.build_v172_release import build_v172_release
from dlcp_fw.patch.build_v33_release import build_v33_release


pytestmark = pytest.mark.dual_supported


def test_build_v33_release_bumps_runtime_and_identity_revision_literals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asm_path = tmp_path / "dlcp_main_v33.asm"
    asm_path.write_text(
        "runtime_identity:\n"
        "        movlw   0x71 ; V3.3_RUNTIME_EEPROM_REV\n"
        "cmd25_identity_query_handler:\n"
        "        movlw       0x07                        ; V3.3_IDENTITY_REV_HI\n"
        "        movlw       0x01                        ; V3.3_IDENTITY_REV_LO\n"
        "org 0xF00000\n"
        "        db      0x03, 0x03, 0x71\n",
        encoding="utf-8",
    )
    output_hex = tmp_path / "DLCP_Firmware_V3.3.hex"

    def _fake_assemble(_asm: Path, out_hex: Path, *, output_lst=None, gpasm="gpasm"):
        out_hex.write_text(":00000001FF\n", encoding="ascii")
        if output_lst is not None:
            output_lst.write_text("; ok\n", encoding="ascii")

    monkeypatch.setattr("dlcp_fw.patch.build_v33_release.assemble_v30", _fake_assemble)

    old_rev, new_rev, built_hex = build_v33_release(
        asm_path=asm_path,
        output_hex=output_hex,
    )

    text = asm_path.read_text(encoding="utf-8")
    assert (old_rev, new_rev, built_hex) == (0x71, 0x72, output_hex)
    assert "movlw   0x72 ; V3.3_RUNTIME_EEPROM_REV" in text
    assert "movlw       0x07                        ; V3.3_IDENTITY_REV_HI" in text
    assert "movlw       0x02                        ; V3.3_IDENTITY_REV_LO" in text
    assert "db      0x03, 0x03, 0x72" in text
    assert output_hex.read_text(encoding="ascii") == ":00000001FF\n"


def test_build_v33_release_rolls_back_source_hex_and_listing_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asm_path = tmp_path / "dlcp_main_v33.asm"
    original_text = (
        "runtime_identity:\n"
        "        movlw   0x71 ; V3.3_RUNTIME_EEPROM_REV\n"
        "cmd25_identity_query_handler:\n"
        "        movlw       0x07                        ; V3.3_IDENTITY_REV_HI\n"
        "        movlw       0x01                        ; V3.3_IDENTITY_REV_LO\n"
        "org 0xF00000\n"
        "        db      0x03, 0x03, 0x71\n"
    )
    asm_path.write_text(original_text, encoding="utf-8")
    lst_path = asm_path.with_suffix(".lst")
    lst_path.write_text("; previous\n", encoding="ascii")
    output_hex = tmp_path / "DLCP_Firmware_V3.3.hex"
    output_hex.write_text(":00000001FF\n", encoding="ascii")

    def _boom(_asm: Path, out_hex: Path, *, output_lst=None, gpasm="gpasm"):
        if output_lst is not None:
            output_lst.write_text("; partial\n", encoding="ascii")
        raise RuntimeError("gpasm boom")

    monkeypatch.setattr("dlcp_fw.patch.build_v33_release.assemble_v30", _boom)

    with pytest.raises(RuntimeError, match="gpasm boom"):
        build_v33_release(asm_path=asm_path, output_hex=output_hex)

    assert asm_path.read_text(encoding="utf-8") == original_text
    assert output_hex.read_text(encoding="ascii") == ":00000001FF\n"
    assert lst_path.read_text(encoding="ascii") == "; previous\n"


def test_build_v172_release_updates_revision_date_and_banner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asm_path = tmp_path / "dlcp_control_v172.asm"
    asm_path.write_text(
        "control_release_banner_row2:\n"
        "        db      0x52, 0x65, 0x76, 0x20, 0x78, 0x33, 0x31, 0x20, 0x32, 0x30, 0x32, 0x36, 0x30, 0x35, 0x32, 0x38, 0x00 ; \"Rev x31 20260528\"\n"
        "control_release_metadata:\n"
        "        db      0x01, 0x07, 0x32, 0x31\n"
        "        db      0x20, 0x26, 0x05, 0x28                    ; build date 20260528 (BCD YYYYMMDD)\n",
        encoding="utf-8",
    )
    output_hex = tmp_path / "DLCP_Control_V1.72.hex"

    def _fake_assemble(_asm_path: Path, hex_out: Path, **_kwargs) -> None:
        hex_out.write_text(":00000001FF\n", encoding="ascii")

    monkeypatch.setattr("dlcp_fw.patch.build_v172_release.assemble_v17", _fake_assemble)

    old_rev, new_rev, built_hex = build_v172_release(
        asm_path=asm_path,
        output_hex=output_hex,
        build_date="20260529",
    )

    text = asm_path.read_text(encoding="utf-8")
    assert (old_rev, new_rev, built_hex) == (0x31, 0x32, output_hex)
    assert "db      0x01, 0x07, 0x32, 0x32" in text
    assert "db      0x20, 0x26, 0x05, 0x29" in text
    assert '"Rev x32 20260529"' in text
    assert output_hex.read_text(encoding="ascii") == ":00000001FF\n"


def test_build_v172_release_rolls_back_source_hex_and_listing_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asm_path = tmp_path / "dlcp_control_v172.asm"
    original_text = (
        "control_release_banner_row2:\n"
        "        db      0x52, 0x65, 0x76, 0x20, 0x78, 0x33, 0x31, 0x20, 0x32, 0x30, 0x32, 0x36, 0x30, 0x35, 0x32, 0x38, 0x00 ; \"Rev x31 20260528\"\n"
        "control_release_metadata:\n"
        "        db      0x01, 0x07, 0x32, 0x31\n"
        "        db      0x20, 0x26, 0x05, 0x28                    ; build date 20260528 (BCD YYYYMMDD)\n"
    )
    asm_path.write_text(original_text, encoding="utf-8")
    lst_path = asm_path.with_suffix(".lst")
    lst_path.write_text("; previous\n", encoding="ascii")
    output_hex = tmp_path / "DLCP_Control_V1.72.hex"
    output_hex.write_text(":00000001FF\n", encoding="ascii")

    def _boom(_asm: Path, out_hex: Path, *, output_lst=None, gpasm="gpasm"):
        if output_lst is not None:
            output_lst.write_text("; partial\n", encoding="ascii")
        raise RuntimeError("gpasm boom")

    monkeypatch.setattr("dlcp_fw.patch.build_v172_release.assemble_v17", _boom)

    with pytest.raises(RuntimeError, match="gpasm boom"):
        build_v172_release(
            asm_path=asm_path,
            output_hex=output_hex,
            build_date="20260529",
        )

    assert asm_path.read_text(encoding="utf-8") == original_text
    assert output_hex.read_text(encoding="ascii") == ":00000001FF\n"
    assert lst_path.read_text(encoding="ascii") == "; previous\n"
