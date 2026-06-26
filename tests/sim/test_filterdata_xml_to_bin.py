from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from dlcp_fw.flash.filterdata_xml import (
    MAX_FILTERDATA_XML_BYTES,
    TABLE_SIZE,
    build_preset_table,
    detect_coefficient_mode,
    first_diff,
    main,
    parse_filterdata_xml,
    sha256_hex,
)
from dlcp_fw.paths import (
    LX521_ARTIFACTS_DIR,
    LX521_FILTERDATA_DIR,
    V35_FILTERDATA_PRESET_A,
    V35_FILTERDATA_PRESET_A_SHA256,
    V35_FILTERDATA_PRESET_B,
    V35_FILTERDATA_PRESET_B_SHA256,
)


pytestmark = pytest.mark.dual_supported

V5_XML = V35_FILTERDATA_PRESET_A / "Config.xml"
V8_XML = V35_FILTERDATA_PRESET_B / "Config.xml"
V7_XML = LX521_FILTERDATA_DIR / "LX521.4 22MG10F-v7" / "Config.xml"
V5_BIN = LX521_ARTIFACTS_DIR / "LX521.4_22MG10F-v5.bin"
V7_BIN = LX521_ARTIFACTS_DIR / "LX521.4_22MG10F-v7.bin"


def _write_synthetic_filterdata(
    path: Path,
    *,
    sample_rate: str = "93750",
    frequency: str = "1000",
    q: str = "1",
    gain: str = "0",
    delay: str = "0",
    process_extra: int = 0,
) -> None:
    root = ET.Element("config")
    ET.SubElement(root, "device", procsamplingrate=sample_rate)
    for group_id in range(1, 7):
        gain_node = ET.SubElement(
            root,
            "processobj",
            processtype="ptGain",
            groupid=str(group_id),
        )
        ET.SubElement(gain_node, "gain", value=gain)
        delay_node = ET.SubElement(
            root,
            "processobj",
            processtype="ptDelay",
            groupid=str(group_id),
        )
        ET.SubElement(delay_node, "delay", value=delay)
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
            ET.SubElement(bq, "gain", value=gain)
            ET.SubElement(bq, "q1", value=q)
            ET.SubElement(bq, "zconst", value="1")
            ET.SubElement(bq, "shelfhl", value="stLowShelf")
            ET.SubElement(bq, "b0", value="1")
            ET.SubElement(bq, "b1", value="0")
            ET.SubElement(bq, "b2", value="0")
            ET.SubElement(bq, "a1", value="0")
            ET.SubElement(bq, "a2", value="0")
    for index in range(process_extra):
        ET.SubElement(root, "processobj", processtype="ptIgnored", groupid="99", title=f"extra {index}")
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _local_fixture_or_skip(*paths: Path) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        pytest.skip(
            "local LX521 FilterData/capture artifacts are absent: " + ", ".join(missing)
        )


def test_synthetic_filterdata_xml_generates_table(tmp_path: Path) -> None:
    xml = tmp_path / "Synthetic" / "Config.xml"
    _write_synthetic_filterdata(xml)

    project = parse_filterdata_xml(xml)
    generated = build_preset_table(xml, mode="hfd-pz")

    assert project.proc_sampling_rate == 93750
    assert len(generated) == TABLE_SIZE
    assert generated[:4] == bytes([0x01, 0xC8, 0x04, 0x00])


def test_hardened_parser_rejects_dtd_entity_payload(tmp_path: Path) -> None:
    xml = tmp_path / "Config.xml"
    xml.write_text(
        "<?xml version='1.0'?><!DOCTYPE x [<!ENTITY e 'x'>]><config>&e;</config>",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="DTD/entity"):
        parse_filterdata_xml(xml)


def test_hardened_parser_rejects_oversized_xml(tmp_path: Path) -> None:
    xml = tmp_path / "Config.xml"
    xml.write_bytes(b"<config>" + (b" " * MAX_FILTERDATA_XML_BYTES) + b"</config>")

    with pytest.raises(RuntimeError, match="max"):
        parse_filterdata_xml(xml)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"sample_rate": "1000"}, "sample rate"),
        ({"frequency": "50000"}, "frequency"),
        ({"q": "0"}, "Q"),
        ({"gain": "99"}, "gain"),
        ({"delay": "9999"}, "delay"),
    ],
)
def test_hardened_parser_rejects_out_of_range_numbers(
    tmp_path: Path,
    kwargs: dict[str, str],
    match: str,
) -> None:
    xml = tmp_path / "Config.xml"
    _write_synthetic_filterdata(xml, **kwargs)

    with pytest.raises(RuntimeError, match=match):
        parse_filterdata_xml(xml)


def test_hardened_parser_rejects_excess_process_nodes(tmp_path: Path) -> None:
    xml = tmp_path / "Config.xml"
    _write_synthetic_filterdata(xml, process_extra=257)

    with pytest.raises(RuntimeError, match="processobj"):
        parse_filterdata_xml(xml)


def test_v5_filterdata_hfd_pz_matches_capture_when_local_fixtures_present() -> None:
    _local_fixture_or_skip(V5_XML, V5_BIN)

    generated = build_preset_table(V5_XML, mode="hfd-pz")
    expected = V5_BIN.read_bytes()

    assert len(generated) == TABLE_SIZE
    assert generated == expected
    assert sha256_hex(generated) == V35_FILTERDATA_PRESET_A_SHA256


def test_v8_filterdata_hfd_pz_sha_when_local_fixture_present() -> None:
    _local_fixture_or_skip(V8_XML)

    generated = build_preset_table(V8_XML, mode="hfd-pz")

    assert len(generated) == TABLE_SIZE
    assert sha256_hex(generated) == V35_FILTERDATA_PRESET_B_SHA256


def test_v7_filterdata_xml_generates_capture_when_local_fixtures_present() -> None:
    _local_fixture_or_skip(V7_XML, V7_BIN)

    generated = build_preset_table(V7_XML)

    assert generated == V7_BIN.read_bytes()
    assert (
        sha256_hex(generated)
        == "35fd6ae514a7d541cc6efd82f9773a7b5c5a3566f7f09589a569df19597fdc22"
    )


def test_filterdata_mode_detection_with_local_fixtures_when_present() -> None:
    _local_fixture_or_skip(V5_XML, V7_XML)

    assert detect_coefficient_mode(parse_filterdata_xml(V5_XML)) == "legacy"
    assert detect_coefficient_mode(parse_filterdata_xml(V7_XML)) == "direct"


def test_v5_default_mode_is_not_the_byte_exact_capture_source_when_local_present() -> None:
    _local_fixture_or_skip(V5_XML, V5_BIN)

    generated = build_preset_table(V5_XML)
    expected = V5_BIN.read_bytes()

    assert generated != expected
    assert first_diff(generated, expected) == (0x001F, 0x15, 0x16)


def test_cli_writes_and_verifies_synthetic_table(tmp_path: Path, capsys) -> None:
    xml = tmp_path / "Synthetic" / "Config.xml"
    expected = tmp_path / "expected.bin"
    out = tmp_path / "out.bin"
    _write_synthetic_filterdata(xml)
    expected.write_bytes(build_preset_table(xml, mode="hfd-pz"))

    rc = main([str(xml), "--mode", "hfd-pz", "--output", str(out), "--verify", str(expected)])
    stdout = capsys.readouterr().out

    assert rc == 0
    assert out.read_bytes() == expected.read_bytes()
    assert "verify: MATCH" in stdout


def test_cli_reports_synthetic_verify_mismatch(tmp_path: Path, capsys) -> None:
    xml = tmp_path / "Synthetic" / "Config.xml"
    expected = tmp_path / "expected.bin"
    out = tmp_path / "out.bin"
    _write_synthetic_filterdata(xml)
    expected.write_bytes(b"\x00" * TABLE_SIZE)

    rc = main([str(xml), "--mode", "hfd-pz", "--output", str(out), "--verify", str(expected)])
    stderr = capsys.readouterr().err

    assert rc == 1
    assert "verify: MISMATCH" in stderr
