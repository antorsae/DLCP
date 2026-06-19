"""V3.5/V1.73 release-builder regression tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.patch.build_v173_release import build_v173_release
from dlcp_fw.patch.build_v35_release import build_v35_release


pytestmark = pytest.mark.dual_supported


_V35_FIXTURE = (
    "runtime_identity:\n"
    "        movlw   0x79 ; V3.5_RUNTIME_EEPROM_REV_LO\n"
    "cmd25_identity_query_handler:\n"
    "        movlw       0x07                        ; V3.5_IDENTITY_REV_LO_HI\n"
    "        movlw       0x09                        ; V3.5_IDENTITY_REV_LO_LO\n"
    "        movlw       0x00                        ; V3.5_IDENTITY_REV_HI_HI\n"
    "        movlw       0x01                        ; V3.5_IDENTITY_REV_HI_LO\n"
    "org 0xF00000\n"
    "        db      0x03, 0x05, 0x79\n"
)

_V173_FIXTURE = (
    "control_release_banner_row2:\n"
    "        db      0x52, 0x65, 0x76, 0x20, 0x78, 0x33, 0x46, 0x20, 0x32, 0x30, 0x32, 0x36, 0x30, 0x36, 0x30, 0x37, 0x00 ; \"Rev x3F 20260607\"\n"
    "control_release_metadata:\n"
    "        db      0x01, 0x07, 0x33, 0x3F\n"
    "        db      0x20, 0x26, 0x06, 0x07                    ; build date 20260607 (BCD YYYYMMDD)\n"
)


def test_build_v35_release_bumps_runtime_identity_and_runs_ram_safety(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asm_path = tmp_path / "dlcp_main_v35.asm"
    asm_path.write_text(_V35_FIXTURE, encoding="utf-8")
    output_hex = tmp_path / "DLCP_Firmware_V3.5.hex"
    events: list[str] = []

    def _fake_assemble(_asm: Path, out_hex: Path, *, output_lst=None, gpasm="gpasm"):
        events.append("assemble")
        out_hex.write_text(":00000001FF\n", encoding="ascii")
        if output_lst is not None:
            output_lst.write_text("; ok\n", encoding="ascii")

    def _fake_ram_safety(targets: list[str]) -> None:
        events.append("ram")
        assert targets == ["main-v35"]
        assert not output_hex.exists()

    monkeypatch.setattr("dlcp_fw.patch.build_v35_release.assemble_v30", _fake_assemble)
    monkeypatch.setattr("dlcp_fw.patch.build_v35_release.assert_targets_safe", _fake_ram_safety)

    old_rev, new_rev, built_hex = build_v35_release(asm_path=asm_path, output_hex=output_hex)

    text = asm_path.read_text(encoding="utf-8")
    assert (old_rev, new_rev, built_hex) == (0x0179, 0x017A, output_hex)
    assert events == ["assemble", "ram"]
    assert "movlw   0x7A ; V3.5_RUNTIME_EEPROM_REV_LO" in text
    assert "movlw       0x07                        ; V3.5_IDENTITY_REV_LO_HI" in text
    assert "movlw       0x0A                        ; V3.5_IDENTITY_REV_LO_LO" in text
    assert "movlw       0x00                        ; V3.5_IDENTITY_REV_HI_HI" in text
    assert "movlw       0x01                        ; V3.5_IDENTITY_REV_HI_LO" in text
    assert "db      0x03, 0x05, 0x7A" in text
    assert output_hex.read_text(encoding="ascii") == ":00000001FF\n"


def test_build_v35_release_wraps_16bit_revision_from_ffff_to_0000(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asm_path = tmp_path / "dlcp_main_v35.asm"
    asm_path.write_text(
        "runtime_identity:\n"
        "        movlw   0xFF ; V3.5_RUNTIME_EEPROM_REV_LO\n"
        "cmd25_identity_query_handler:\n"
        "        movlw       0x0F                        ; V3.5_IDENTITY_REV_LO_HI\n"
        "        movlw       0x0F                        ; V3.5_IDENTITY_REV_LO_LO\n"
        "        movlw       0x0F                        ; V3.5_IDENTITY_REV_HI_HI\n"
        "        movlw       0x0F                        ; V3.5_IDENTITY_REV_HI_LO\n"
        "org 0xF00000\n"
        "        db      0x03, 0x05, 0xFF\n",
        encoding="utf-8",
    )
    output_hex = tmp_path / "DLCP_Firmware_V3.5.hex"
    events: list[str] = []

    def _fake_assemble(_asm: Path, out_hex: Path, *, output_lst=None, gpasm="gpasm"):
        events.append("assemble")
        out_hex.write_text(":00000001FF\n", encoding="ascii")
        if output_lst is not None:
            output_lst.write_text("; ok\n", encoding="ascii")

    def _fake_ram_safety(targets: list[str]) -> None:
        events.append("ram")
        assert targets == ["main-v35"]

    monkeypatch.setattr("dlcp_fw.patch.build_v35_release.assemble_v30", _fake_assemble)
    monkeypatch.setattr("dlcp_fw.patch.build_v35_release.assert_targets_safe", _fake_ram_safety)

    old_rev, new_rev, built_hex = build_v35_release(asm_path=asm_path, output_hex=output_hex)

    text = asm_path.read_text(encoding="utf-8")
    assert (old_rev, new_rev, built_hex) == (0xFFFF, 0x0000, output_hex)
    assert events == ["assemble", "ram"]
    assert "movlw   0x00 ; V3.5_RUNTIME_EEPROM_REV_LO" in text
    assert "movlw       0x00                        ; V3.5_IDENTITY_REV_LO_HI" in text
    assert "movlw       0x00                        ; V3.5_IDENTITY_REV_LO_LO" in text
    assert "movlw       0x00                        ; V3.5_IDENTITY_REV_HI_HI" in text
    assert "movlw       0x00                        ; V3.5_IDENTITY_REV_HI_LO" in text
    assert "db      0x03, 0x05, 0x00" in text
    assert output_hex.read_text(encoding="ascii") == ":00000001FF\n"


def test_build_v35_release_rolls_back_source_hex_and_listing_on_assembly_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asm_path = tmp_path / "dlcp_main_v35.asm"
    asm_path.write_text(_V35_FIXTURE, encoding="utf-8")
    lst_path = asm_path.with_suffix(".lst")
    lst_path.write_text("; previous\n", encoding="ascii")
    output_hex = tmp_path / "DLCP_Firmware_V3.5.hex"
    output_hex.write_text(":old\n", encoding="ascii")

    def _boom(_asm: Path, _out_hex: Path, *, output_lst=None, gpasm="gpasm"):
        if output_lst is not None:
            output_lst.write_text("; partial\n", encoding="ascii")
        raise RuntimeError("gpasm boom")

    monkeypatch.setattr("dlcp_fw.patch.build_v35_release.assemble_v30", _boom)

    with pytest.raises(RuntimeError, match="gpasm boom"):
        build_v35_release(asm_path=asm_path, output_hex=output_hex)

    assert asm_path.read_text(encoding="utf-8") == _V35_FIXTURE
    assert output_hex.read_text(encoding="ascii") == ":old\n"
    assert lst_path.read_text(encoding="ascii") == "; previous\n"


def test_build_v35_release_rolls_back_when_ram_safety_fails_before_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asm_path = tmp_path / "dlcp_main_v35.asm"
    asm_path.write_text(_V35_FIXTURE, encoding="utf-8")
    lst_path = asm_path.with_suffix(".lst")
    lst_path.write_text("; previous\n", encoding="ascii")
    output_hex = tmp_path / "DLCP_Firmware_V3.5.hex"
    output_hex.write_text(":old\n", encoding="ascii")

    def _fake_assemble(_asm: Path, out_hex: Path, *, output_lst=None, gpasm="gpasm"):
        out_hex.write_text(":new\n", encoding="ascii")
        if output_lst is not None:
            output_lst.write_text("; partial\n", encoding="ascii")

    def _unsafe(_targets: list[str]) -> None:
        raise RuntimeError("RAM safety failed")

    monkeypatch.setattr("dlcp_fw.patch.build_v35_release.assemble_v30", _fake_assemble)
    monkeypatch.setattr("dlcp_fw.patch.build_v35_release.assert_targets_safe", _unsafe)

    with pytest.raises(RuntimeError, match="RAM safety failed"):
        build_v35_release(asm_path=asm_path, output_hex=output_hex)

    assert asm_path.read_text(encoding="utf-8") == _V35_FIXTURE
    assert output_hex.read_text(encoding="ascii") == ":old\n"
    assert lst_path.read_text(encoding="ascii") == "; previous\n"


def test_build_v173_release_updates_revision_date_banner_and_runs_ram_safety(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asm_path = tmp_path / "dlcp_control_v173.asm"
    asm_path.write_text(_V173_FIXTURE, encoding="utf-8")
    output_hex = tmp_path / "DLCP_Control_V1.73.hex"
    events: list[str] = []

    def _fake_assemble(_asm_path: Path, hex_out: Path, **_kwargs) -> None:
        events.append("assemble")
        hex_out.write_text(":00000001FF\n", encoding="ascii")
        output_lst = _kwargs.get("output_lst")
        if output_lst is not None:
            output_lst.write_text("; ok\n", encoding="ascii")

    def _fake_ram_safety(targets: list[str]) -> None:
        events.append("ram")
        assert targets == ["control-v173"]
        assert not output_hex.exists()

    monkeypatch.setattr("dlcp_fw.patch.build_v173_release.assemble_v17", _fake_assemble)
    monkeypatch.setattr("dlcp_fw.patch.build_v173_release.assert_targets_safe", _fake_ram_safety)

    old_rev, new_rev, built_hex = build_v173_release(
        asm_path=asm_path,
        output_hex=output_hex,
        build_date="20260608",
    )

    text = asm_path.read_text(encoding="utf-8")
    assert (old_rev, new_rev, built_hex) == (0x3F, 0x40, output_hex)
    assert events == ["assemble", "ram"]
    assert "db      0x01, 0x07, 0x33, 0x40" in text
    assert "db      0x20, 0x26, 0x06, 0x08" in text
    assert '"Rev x40 20260608"' in text
    assert output_hex.read_text(encoding="ascii") == ":00000001FF\n"


def test_build_v173_release_rolls_back_source_hex_and_listing_on_assembly_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asm_path = tmp_path / "dlcp_control_v173.asm"
    asm_path.write_text(_V173_FIXTURE, encoding="utf-8")
    lst_path = asm_path.with_suffix(".lst")
    lst_path.write_text("; previous\n", encoding="ascii")
    output_hex = tmp_path / "DLCP_Control_V1.73.hex"
    output_hex.write_text(":old\n", encoding="ascii")

    def _boom(_asm: Path, _out_hex: Path, *, output_lst=None, gpasm="gpasm"):
        if output_lst is not None:
            output_lst.write_text("; partial\n", encoding="ascii")
        raise RuntimeError("gpasm boom")

    monkeypatch.setattr("dlcp_fw.patch.build_v173_release.assemble_v17", _boom)

    with pytest.raises(RuntimeError, match="gpasm boom"):
        build_v173_release(asm_path=asm_path, output_hex=output_hex, build_date="20260608")

    assert asm_path.read_text(encoding="utf-8") == _V173_FIXTURE
    assert output_hex.read_text(encoding="ascii") == ":old\n"
    assert lst_path.read_text(encoding="ascii") == "; previous\n"


def test_build_v173_release_rolls_back_when_ram_safety_fails_before_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asm_path = tmp_path / "dlcp_control_v173.asm"
    asm_path.write_text(_V173_FIXTURE, encoding="utf-8")
    lst_path = asm_path.with_suffix(".lst")
    lst_path.write_text("; previous\n", encoding="ascii")
    output_hex = tmp_path / "DLCP_Control_V1.73.hex"
    output_hex.write_text(":old\n", encoding="ascii")

    def _fake_assemble(_asm: Path, out_hex: Path, *, output_lst=None, gpasm="gpasm"):
        out_hex.write_text(":new\n", encoding="ascii")
        if output_lst is not None:
            output_lst.write_text("; partial\n", encoding="ascii")

    def _unsafe(_targets: list[str]) -> None:
        raise RuntimeError("RAM safety failed")

    monkeypatch.setattr("dlcp_fw.patch.build_v173_release.assemble_v17", _fake_assemble)
    monkeypatch.setattr("dlcp_fw.patch.build_v173_release.assert_targets_safe", _unsafe)

    with pytest.raises(RuntimeError, match="RAM safety failed"):
        build_v173_release(asm_path=asm_path, output_hex=output_hex, build_date="20260608")

    assert asm_path.read_text(encoding="utf-8") == _V173_FIXTURE
    assert output_hex.read_text(encoding="ascii") == ":old\n"
    assert lst_path.read_text(encoding="ascii") == "; previous\n"
