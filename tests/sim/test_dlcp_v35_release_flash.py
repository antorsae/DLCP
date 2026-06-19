from __future__ import annotations

import json
from pathlib import Path

import pytest

from dlcp_fw.flash import dlcp_v35_release_flash as release_flash


pytestmark = pytest.mark.dual_supported


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="ascii")


def _write_capture_pair(bin_path: Path, meta_path: Path, *, fill: int, name: str) -> None:
    bin_path.parent.mkdir(parents=True, exist_ok=True)
    bin_path.write_bytes(bytes([fill & 0xFF]) * 0x0A00)
    meta_path.write_text(
        json.dumps(
            {
                "config_name": name,
                "config_name_raw_hex": name.encode("ascii").ljust(0x1E, b"\xFF").hex(),
            }
        ),
        encoding="utf-8",
    )


def test_main_left_forwards_canonical_v35_release_args(monkeypatch, tmp_path) -> None:
    release_hex = tmp_path / "DLCP_Firmware_V3.5.hex"
    capture_a = tmp_path / "LX521.4_22MG10F-v5.bin"
    meta_a = tmp_path / "LX521.4_22MG10F-v5.json"
    capture_b = tmp_path / "LX521.4_22MG10F-v7.bin"
    meta_b = tmp_path / "LX521.4_22MG10F-v7.json"
    for path in (release_hex, capture_a, meta_a, capture_b, meta_b):
        _touch(path)

    monkeypatch.setattr(release_flash, "V35_MAIN_HEX", release_hex)
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


def test_main_missing_local_captures_warns_and_flashes_unbaked_v35_release(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    release_hex = tmp_path / "DLCP_Firmware_V3.5.hex"
    _touch(release_hex)

    monkeypatch.setattr(release_flash, "V35_MAIN_HEX", release_hex)
    monkeypatch.setattr(
        release_flash,
        "CAPTURE_A_BIN",
        tmp_path / "artifacts" / "LX521.4" / "LX521.4_22MG10F-v5.bin",
    )
    monkeypatch.setattr(
        release_flash,
        "CAPTURE_A_META",
        tmp_path / "artifacts" / "LX521.4" / "LX521.4_22MG10F-v5.json",
    )
    monkeypatch.setattr(
        release_flash,
        "CAPTURE_B_BIN",
        tmp_path / "artifacts" / "LX521.4" / "LX521.4_22MG10F-v7.bin",
    )
    monkeypatch.setattr(
        release_flash,
        "CAPTURE_B_META",
        tmp_path / "artifacts" / "LX521.4" / "LX521.4_22MG10F-v7.json",
    )

    seen: dict[str, list[str]] = {}

    def _fake_main(argv: list[str]) -> int:
        seen["argv"] = argv
        return 0

    monkeypatch.setattr(release_flash.main_flash, "main", _fake_main)

    rc = release_flash.main(["--left"])

    assert rc == 0
    assert seen["argv"] == ["--hex", str(release_hex), "--all-ch", "L"]
    out = capsys.readouterr().out
    assert "WARNING: local A/B preset captures are incomplete" in out
    assert "without baked presets" in out
    assert "Hypex Filter Design" in out
    assert "artifacts/LX521.4/" in out


def test_main_explicit_rc5_profile_forwards_to_main_flasher(monkeypatch, tmp_path) -> None:
    release_hex = tmp_path / "DLCP_Firmware_V3.5.hex"
    _touch(release_hex)

    monkeypatch.setattr(release_flash, "V35_MAIN_HEX", release_hex)
    monkeypatch.setattr(
        release_flash,
        "CAPTURE_A_BIN",
        tmp_path / "artifacts" / "LX521.4" / "LX521.4_22MG10F-v5.bin",
    )
    monkeypatch.setattr(
        release_flash,
        "CAPTURE_A_META",
        tmp_path / "artifacts" / "LX521.4" / "LX521.4_22MG10F-v5.json",
    )
    monkeypatch.setattr(
        release_flash,
        "CAPTURE_B_BIN",
        tmp_path / "artifacts" / "LX521.4" / "LX521.4_22MG10F-v7.bin",
    )
    monkeypatch.setattr(
        release_flash,
        "CAPTURE_B_META",
        tmp_path / "artifacts" / "LX521.4" / "LX521.4_22MG10F-v7.json",
    )

    seen: dict[str, list[str]] = {}

    def _fake_main(argv: list[str]) -> int:
        seen["argv"] = argv
        return 0

    monkeypatch.setattr(release_flash.main_flash, "main", _fake_main)

    rc = release_flash.main(["--left", "--profile", "rc5"])

    assert rc == 0
    assert seen["argv"] == [
        "--hex",
        str(release_hex),
        "--all-ch",
        "L",
        "--profile",
        "rc5",
    ]


def test_info_only_passthrough_does_not_require_v35_release_artifacts(monkeypatch) -> None:
    seen: dict[str, list[str]] = {}

    def _fake_main(argv: list[str]) -> int:
        seen["argv"] = argv
        return 0

    monkeypatch.setattr(release_flash.main_flash, "main", _fake_main)

    rc = release_flash.main(["--info-only"])

    assert rc == 0
    assert seen["argv"] == ["--info-only"]


def test_v35_flash_requires_explicit_route(monkeypatch) -> None:
    monkeypatch.setattr(release_flash.main_flash, "main", lambda argv: 0)
    with pytest.raises(SystemExit) as exc:
        release_flash.main([])
    assert exc.value.code == 2


def test_main_left_preflight_with_real_v35_hex_and_local_captures(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    capture_a = tmp_path / "LX521.4_22MG10F-v5.bin"
    meta_a = tmp_path / "LX521.4_22MG10F-v5.json"
    capture_b = tmp_path / "LX521.4_22MG10F-v7.bin"
    meta_b = tmp_path / "LX521.4_22MG10F-v7.json"
    _write_capture_pair(capture_a, meta_a, fill=0xA5, name="preset A")
    _write_capture_pair(capture_b, meta_b, fill=0x5A, name="preset B")

    monkeypatch.setattr(release_flash, "CAPTURE_A_BIN", capture_a)
    monkeypatch.setattr(release_flash, "CAPTURE_A_META", meta_a)
    monkeypatch.setattr(release_flash, "CAPTURE_B_BIN", capture_b)
    monkeypatch.setattr(release_flash, "CAPTURE_B_META", meta_b)

    rc = release_flash.main(["--left", "--preflight-only"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "preflight: OK" in out
    assert "target firmware version: 3.5" in out
