from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from dlcp_fw.flash import dlcp_v35_release_flash as release_flash
from dlcp_fw.flash.filterdata_xml import build_preset_table, sha256_hex


pytestmark = pytest.mark.dual_supported


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="ascii")


def _write_minimal_main_hex(path: Path) -> None:
    from dlcp_fw.sim.hexio import write_intel_hex

    addr = 0x240C
    write_intel_hex(
        path,
        {
            0x1000: 0x11,
            addr + 0: 0x03,
            addr + 1: 0x0E,
            addr + 2: 0x01,
            addr + 3: 0x01,
            addr + 4: 0x5B,
            addr + 5: 0x6F,
            addr + 6: 0x03,
            addr + 7: 0x0E,
            addr + 8: 0x5C,
            addr + 9: 0x6F,
            addr + 10: 0x05,
            addr + 11: 0x0E,
            addr + 12: 0x5D,
            addr + 13: 0x6F,
        },
    )


def _write_filterdata_xml(path: Path, *, frequency: str = "1000") -> None:
    root = ET.Element("config")
    ET.SubElement(root, "device", procsamplingrate="93750")
    for group_id in range(1, 7):
        gain_node = ET.SubElement(root, "processobj", processtype="ptGain", groupid=str(group_id))
        ET.SubElement(gain_node, "gain", value="0")
        delay_node = ET.SubElement(root, "processobj", processtype="ptDelay", groupid=str(group_id))
        ET.SubElement(delay_node, "delay", value="0")
        for index in range(1, 16):
            bq = ET.SubElement(
                root,
                "processobj",
                processtype="ptBiQuad",
                groupid=str(group_id),
                title=f"BQ {index}",
                enabled="true",
            )
            ET.SubElement(bq, "filtertype", value="ftUnity")
            ET.SubElement(bq, "f1", value=frequency)
            ET.SubElement(bq, "gain", value="0")
            ET.SubElement(bq, "q1", value="1")
            ET.SubElement(bq, "zconst", value="1")
            ET.SubElement(bq, "shelfhl", value="stLowShelf")
            ET.SubElement(bq, "b0", value="1")
            ET.SubElement(bq, "b1", value="0")
            ET.SubElement(bq, "b2", value="0")
            ET.SubElement(bq, "a1", value="0")
            ET.SubElement(bq, "a2", value="0")
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _patch_release_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    write_xml: bool = True,
) -> tuple[Path, Path, Path]:
    release_hex = tmp_path / "DLCP_Firmware_V3.5.hex"
    filterdata_a = tmp_path / "LX521.4 22MG10F-v5"
    filterdata_b = tmp_path / "LX521.4 22MG10F-v8"
    _write_minimal_main_hex(release_hex)
    if write_xml:
        _write_filterdata_xml(filterdata_a / "Config.xml")
        _write_filterdata_xml(filterdata_b / "Config.xml", frequency="1200")

    monkeypatch.setattr(release_flash, "V35_MAIN_HEX", release_hex)
    monkeypatch.setattr(release_flash, "FILTERDATA_A", filterdata_a)
    monkeypatch.setattr(release_flash, "FILTERDATA_B", filterdata_b)
    monkeypatch.setattr(release_flash, "FILTERDATA_A_NAME", "LX521.4 22MG10F-v5")
    monkeypatch.setattr(release_flash, "FILTERDATA_B_NAME", "LX521.4 22MG10F-v8")
    monkeypatch.setattr(
        release_flash,
        "FILTERDATA_A_SHA256",
        sha256_hex(build_preset_table(filterdata_a / "Config.xml", mode="hfd-pz"))
        if write_xml
        else "0" * 64,
    )
    monkeypatch.setattr(
        release_flash,
        "FILTERDATA_B_SHA256",
        sha256_hex(build_preset_table(filterdata_b / "Config.xml", mode="hfd-pz"))
        if write_xml
        else "0" * 64,
    )
    return release_hex, filterdata_a, filterdata_b


def test_main_left_forwards_canonical_v35_filterdata_args(monkeypatch, tmp_path) -> None:
    release_hex, filterdata_a, filterdata_b = _patch_release_inputs(monkeypatch, tmp_path)

    seen: dict[str, list[str]] = {}

    def _fake_main(argv: list[str]) -> int:
        seen["argv"] = argv
        return 0

    monkeypatch.setattr(release_flash.main_flash, "main", _fake_main)

    rc = release_flash.main(["--left"])

    assert rc == 0
    assert seen["argv"] == [
        "--hex",
        str(release_hex),
        "--filterdata-a",
        str(filterdata_a),
        "--filterdata-b",
        str(filterdata_b),
        "--filterdata-mode",
        "hfd-pz",
        "--all-ch",
        "L",
        "--filterdata-a-name",
        "LX521.4 22MG10F-v5",
        "--filterdata-b-name",
        "LX521.4 22MG10F-v8",
        "--filterdata-a-sha256",
        release_flash.FILTERDATA_A_SHA256,
        "--filterdata-b-sha256",
        release_flash.FILTERDATA_B_SHA256,
    ]


def test_main_missing_local_captures_are_ignored_when_filterdata_exists(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    _patch_release_inputs(monkeypatch, tmp_path)
    seen: dict[str, list[str]] = {}

    def _fake_main(argv: list[str]) -> int:
        seen["argv"] = argv
        return 0

    monkeypatch.setattr(
        release_flash.main_flash,
        "main",
        _fake_main,
    )

    rc = release_flash.main(["--right"])

    assert rc == 0
    assert "--capture-a" not in seen["argv"]
    assert "--meta-a" not in seen["argv"]
    assert "--filterdata-a" in seen["argv"]
    assert "WARNING: local A/B preset captures are incomplete" not in capsys.readouterr().out


def test_main_explicit_rc5_profile_forwards_to_main_flasher(monkeypatch, tmp_path) -> None:
    _patch_release_inputs(monkeypatch, tmp_path)
    seen: dict[str, list[str]] = {}

    def _fake_main(argv: list[str]) -> int:
        seen["argv"] = argv
        return 0

    monkeypatch.setattr(
        release_flash.main_flash,
        "main",
        _fake_main,
    )

    rc = release_flash.main(["--left", "--profile", "rc5"])

    assert rc == 0
    assert seen["argv"][-2:] == ["--profile", "rc5"]
    assert "--filterdata-mode" in seen["argv"]


def test_info_only_passthrough_does_not_require_v35_release_artifacts(monkeypatch) -> None:
    seen: dict[str, list[str]] = {}

    def _fake_main(argv: list[str]) -> int:
        seen["argv"] = argv
        return 0

    monkeypatch.setattr(release_flash.main_flash, "main", _fake_main)

    rc = release_flash.main(["--info-only"])

    assert rc == 0
    assert seen["argv"] == ["--info-only"]


def test_finalize_only_profile_passthrough_does_not_require_filterdata(monkeypatch) -> None:
    seen: dict[str, list[str]] = {}

    def _fake_main(argv: list[str]) -> int:
        seen["argv"] = argv
        return 0

    monkeypatch.setattr(release_flash.main_flash, "main", _fake_main)

    rc = release_flash.main(["--finalize-only", "--profile", "rc5"])

    assert rc == 0
    assert seen["argv"] == ["--finalize-only", "--profile", "rc5"]


def test_v35_flash_requires_explicit_route(monkeypatch) -> None:
    monkeypatch.setattr(release_flash.main_flash, "main", lambda argv: 0)
    with pytest.raises(SystemExit) as exc:
        release_flash.main([])
    assert exc.value.code == 2


def test_missing_filterdata_is_hard_error_before_main_flash(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    _, filterdata_a, filterdata_b = _patch_release_inputs(
        monkeypatch,
        tmp_path,
        write_xml=False,
    )
    monkeypatch.setattr(
        release_flash.main_flash,
        "main",
        lambda argv: (_ for _ in ()).throw(AssertionError("main_flash must not be called")),
    )

    with pytest.raises(SystemExit) as exc:
        release_flash.main(["--left"])

    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert str(filterdata_a / "Config.xml") in err
    assert str(filterdata_b / "Config.xml") in err
    assert "Populate artifacts/LX521.4/FilterData" in err


def test_v35_preflight_rejects_filterdata_sha_mismatch_before_flash_main(
    monkeypatch,
    tmp_path,
) -> None:
    _patch_release_inputs(monkeypatch, tmp_path)
    monkeypatch.setattr(release_flash, "FILTERDATA_A_SHA256", "0" * 64)
    monkeypatch.setattr(
        release_flash.main_flash,
        "flash_main",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("flash_main must not be called")),
    )

    with pytest.raises(SystemExit) as exc:
        release_flash.main(["--left", "--preflight-only"])

    assert exc.value.code == 2


def test_v35_allow_unverified_filterdata_is_noisy_and_continues(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    _patch_release_inputs(monkeypatch, tmp_path)
    monkeypatch.setattr(release_flash, "FILTERDATA_A_SHA256", "0" * 64)
    monkeypatch.setattr(release_flash.main_flash, "flash_main", lambda **kwargs: None)

    rc = release_flash.main(["--left", "--preflight-only", "--allow-unverified-filterdata"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "WARNING: FilterData preset A verification failed" in out
    assert "preflight: OK" in out


def test_v35_help_mentions_filterdata_defaults(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        release_flash.main(["--help"])

    out = capsys.readouterr().out
    assert exc.value.code == 0
    assert "FilterData XML presets" in out
    assert "--allow-unverified-filterdata" in out
    assert "hfd-pz" in out


def test_main_left_preflight_with_synthetic_filterdata(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    _patch_release_inputs(monkeypatch, tmp_path)
    monkeypatch.setattr(release_flash.main_flash, "flash_main", lambda **kwargs: None)

    rc = release_flash.main(["--left", "--preflight-only"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "preflight: OK" in out
    assert "target firmware version: 3.5" in out
    assert "filterdata A mode: hfd-pz" in out
    assert "filterdata B mode: hfd-pz" in out
    assert "filterdata A name: 'LX521.4 22MG10F-v5'" in out
    assert "filterdata B name: 'LX521.4 22MG10F-v8'" in out
    assert "filterdata A flash base: 0x5600" in out
    assert "filterdata B flash base: 0x4C00" in out
    assert "without baked presets" not in out
    assert not list(tmp_path.rglob("*.bin"))
    assert not list(tmp_path.rglob("*.json"))
