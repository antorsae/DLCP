from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.flash import dlcp_v32_release_flash as release_flash


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="ascii")


def test_main_left_forwards_canonical_release_args(monkeypatch, tmp_path) -> None:
    release_hex = tmp_path / "DLCP_Firmware_V3.2.hex"
    capture_a = tmp_path / "LX521.4_22MG10F-v5.bin"
    meta_a = tmp_path / "LX521.4_22MG10F-v5.json"
    capture_b = tmp_path / "LX521.4_22MG10F-v7.bin"
    meta_b = tmp_path / "LX521.4_22MG10F-v7.json"
    for path in (release_hex, capture_a, meta_a, capture_b, meta_b):
        _touch(path)

    monkeypatch.setattr(release_flash, "V32_MAIN_HEX", release_hex)
    monkeypatch.setattr(release_flash, "CAPTURE_A_BIN", capture_a)
    monkeypatch.setattr(release_flash, "CAPTURE_A_META", meta_a)
    monkeypatch.setattr(release_flash, "CAPTURE_B_BIN", capture_b)
    monkeypatch.setattr(release_flash, "CAPTURE_B_META", meta_b)

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
        "--capture-a",
        str(capture_a),
        "--meta-a",
        str(meta_a),
        "--capture-b",
        str(capture_b),
        "--meta-b",
        str(meta_b),
        "--all-ch",
        "L",
    ]


def test_main_all_ch_right_supports_dry_run(monkeypatch, tmp_path) -> None:
    release_hex = tmp_path / "DLCP_Firmware_V3.2.hex"
    capture_a = tmp_path / "LX521.4_22MG10F-v5.bin"
    meta_a = tmp_path / "LX521.4_22MG10F-v5.json"
    capture_b = tmp_path / "LX521.4_22MG10F-v7.bin"
    meta_b = tmp_path / "LX521.4_22MG10F-v7.json"
    for path in (release_hex, capture_a, meta_a, capture_b, meta_b):
        _touch(path)

    monkeypatch.setattr(release_flash, "V32_MAIN_HEX", release_hex)
    monkeypatch.setattr(release_flash, "CAPTURE_A_BIN", capture_a)
    monkeypatch.setattr(release_flash, "CAPTURE_A_META", meta_a)
    monkeypatch.setattr(release_flash, "CAPTURE_B_BIN", capture_b)
    monkeypatch.setattr(release_flash, "CAPTURE_B_META", meta_b)

    seen: dict[str, list[str]] = {}

    def _fake_main(argv: list[str]) -> int:
        seen["argv"] = argv
        return 0

    monkeypatch.setattr(release_flash.main_flash, "main", _fake_main)

    rc = release_flash.main(["--all-ch", "R", "--dry-run", "--verbose"])

    assert rc == 0
    assert seen["argv"] == [
        "--dry-run",
        "--verbose",
        "--hex",
        str(release_hex),
        "--capture-a",
        str(capture_a),
        "--meta-a",
        str(meta_a),
        "--capture-b",
        str(capture_b),
        "--meta-b",
        str(meta_b),
        "--all-ch",
        "R",
    ]


def test_info_only_passthrough_does_not_require_release_artifacts(monkeypatch) -> None:
    seen: dict[str, list[str]] = {}

    def _fake_main(argv: list[str]) -> int:
        seen["argv"] = argv
        return 0

    monkeypatch.setattr(release_flash.main_flash, "main", _fake_main)

    rc = release_flash.main(["--info-only"])

    assert rc == 0
    assert seen["argv"] == ["--info-only"]


def test_flash_requires_explicit_route(monkeypatch) -> None:
    monkeypatch.setattr(release_flash.main_flash, "main", lambda argv: 0)
    with pytest.raises(SystemExit) as exc:
        release_flash.main([])
    assert exc.value.code == 2
