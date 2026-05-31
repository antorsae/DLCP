from __future__ import annotations

import json

from dlcp_fw.cli import hardware_lcd_probe as lcd


def test_raw_ordered_rows_do_not_snap_preset_filename_to_active() -> None:
    observations = [
        lcd.OcrObservation(text="Preset", confidence=0.99, x=0.05, y=0.85, w=0.20, h=0.10),
        lcd.OcrObservation(text="A", confidence=0.92, x=0.90, y=0.85, w=0.05, h=0.10),
        lcd.OcrObservation(text="521.4 22MG10F-v5", confidence=0.91, x=0.05, y=0.30, w=0.70, h=0.10),
    ]

    raw_line1, raw_line2 = lcd._raw_ordered_rows(observations)
    line1, line2 = lcd._pick_lines(observations)

    assert raw_line1 == "Preset A"
    assert raw_line2 == "521.4 22MG10F-v5"
    assert line1 == "Preset"
    assert line2 is None


def test_reconstruct_scroll_windows_stitches_ordered_filename_views() -> None:
    reconstructed = lcd.reconstruct_scroll_windows(
        [
            "521.4 22MG10F-v5",
            "X521.4 22MG10F-",
            "LX521.4 22MG10F",
        ]
    )

    assert reconstructed == "LX521.4 22MG10F-v5"


def test_probe_raw_ordered_row_summary_includes_scroll_reconstruction(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(lcd, "_configure_camera", lambda args: {})
    monkeypatch.setattr(lcd, "_capture_frame", lambda *args, **kwargs: None)
    samples = iter(
        [
            [
                lcd.OcrObservation(text="Preset", confidence=0.99, x=0.05, y=0.85, w=0.20, h=0.10),
                lcd.OcrObservation(text="521.4 22MG10F-v5", confidence=0.90, x=0.05, y=0.30, w=0.70, h=0.10),
            ],
            [
                lcd.OcrObservation(text="Preset", confidence=0.99, x=0.05, y=0.85, w=0.20, h=0.10),
                lcd.OcrObservation(text="X521.4 22MG10F-", confidence=0.90, x=0.05, y=0.30, w=0.70, h=0.10),
            ],
        ]
    )
    monkeypatch.setattr(lcd, "_ocr_frame", lambda *_args: next(samples))

    rc = lcd.main(
        [
            "--captures",
            "2",
            "--output-root",
            str(tmp_path),
            "--skip-configure",
            "--raw-ordered-row",
        ]
    )

    assert rc == 0
    summary_path = sorted((tmp_path / "runs").glob("*/summary.json"))[-1]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["raw_ordered_row"] is True
    assert summary["consensus"]["raw_line1"] == "Preset"
    assert summary["scroll_reconstruction"]["line2"] == "X521.4 22MG10F-v5"
