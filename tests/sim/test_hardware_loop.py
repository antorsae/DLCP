from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from dlcp_fw.cli import hardware_loop as hw
from dlcp_fw.flash.dlcp_main_flash import CaptureOverlay, FILENAME_LEN, PRESET_A_FLASH_BASE, PRESET_TABLE_SIZE, RouteEntry
from dlcp_fw.sim.hexio import parse_intel_hex, write_intel_hex


def _write_capture_a_fixture(tmp_path: Path) -> tuple[Path, Path, bytes, bytes]:
    capture = tmp_path / "presetA.bin"
    sidecar = tmp_path / "presetA.json"
    table = bytes((i & 0xFF) for i in range(PRESET_TABLE_SIZE))
    name_slot = b"ALPHA-A" + (b"\xFF" * (FILENAME_LEN - 7))
    capture.write_bytes(table)
    sidecar.write_text(
        json.dumps(
            {
                "format": "dlcp_preset_capture_v1",
                "preset": "A",
                "config_name": "ALPHA-A",
                "config_name_raw_hex": name_slot.hex(),
            }
        ),
        encoding="ascii",
    )
    return capture, sidecar, table, name_slot


def test_load_avfoundation_audio_inputs_parses_ffmpeg_listing(monkeypatch) -> None:
    sample = """
[AVFoundation indev @ 0x123] AVFoundation video devices:
[AVFoundation indev @ 0x123] [0] Camera
[AVFoundation indev @ 0x123] AVFoundation audio devices:
[AVFoundation indev @ 0x123] [0] BlackHole 2ch
[AVFoundation indev @ 0x123] [1] UMIK-2
[AVFoundation indev @ 0x123] [2] MacBook Pro Microphone
Error opening input files: Input/output error
""".strip()

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 251, stdout="", stderr=sample)

    monkeypatch.setattr(hw, "_run", fake_run)
    devices = hw._load_avfoundation_audio_inputs()
    assert [(dev.name, dev.avfoundation_index) for dev in devices] == [
        ("BlackHole 2ch", 0),
        ("UMIK-2", 1),
        ("MacBook Pro Microphone", 2),
    ]


def test_write_sweep_creates_wav_and_manifest(tmp_path: Path) -> None:
    out = tmp_path / "stimulus.wav"
    spec = hw.SweepSpec(
        sample_rate=48_000,
        start_hz=20.0,
        end_hz=20_000.0,
        sweep_s=1.0,
        pre_s=0.1,
        post_s=0.2,
        amplitude=0.25,
        channels=2,
        fade_s=0.01,
    )
    manifest = hw._write_sweep(out, spec)
    assert out.exists()
    assert manifest.sample_rate == 48_000
    assert manifest.channels == 2
    rate, data = hw._read_wav(out)
    assert rate == 48_000
    assert data.ndim == 2
    expected_len = int(round(spec.total_s * spec.sample_rate))
    assert data.shape == (expected_len, 2)
    assert np.max(np.abs(data)) > 0.1


def test_prepare_flash_hex_bakes_preset_a_and_manifest(tmp_path: Path) -> None:
    base_hex = tmp_path / "base.hex"
    write_intel_hex(base_hex, {0x1000: 0x11})
    capture, sidecar, table, _name_slot = _write_capture_a_fixture(tmp_path)

    flashed_hex, flashed_manifest, overlay = hw._prepare_flash_hex(
        base_hex=base_hex,
        capture_a=capture,
        meta_a=sidecar,
        name_a=None,
        out_dir=tmp_path / "fw",
    )

    assert overlay is not None
    assert overlay.config_name == "ALPHA-A"
    assert overlay.flash_base == PRESET_A_FLASH_BASE
    mem = parse_intel_hex(flashed_hex)
    assert bytes(mem.get(PRESET_A_FLASH_BASE + i, 0xFF) for i in range(0x20)) == table[:0x20]

    manifest = json.loads(flashed_manifest.read_text(encoding="utf-8"))
    assert manifest["base_hex"] == str(base_hex)
    assert manifest["flashed_hex"] == str(flashed_hex)
    assert manifest["preset_a"]["config_name"] == "ALPHA-A"
    assert manifest["preset_a"]["flash_base"] == PRESET_A_FLASH_BASE
    assert manifest["preset_a"]["table_sha256"] == hashlib.sha256(table).hexdigest()


def test_flash_and_finalize_verifies_overlay_and_routes(monkeypatch, tmp_path: Path) -> None:
    flashed_hex = tmp_path / "firmware.hex"
    write_intel_hex(flashed_hex, {0x1000: 0x11})
    _capture, _sidecar, table, name_slot = _write_capture_a_fixture(tmp_path)
    overlay = CaptureOverlay(
        preset="A",
        table=table,
        name_slot=name_slot,
        config_name="ALPHA-A",
        flash_base=PRESET_A_FLASH_BASE,
    )
    seen: dict[str, object] = {}

    def fake_parse_intel_hex(path):
        seen.setdefault("parsed", []).append(str(path))
        return {0x1000: 0x11}

    def fake_run_preflight(**kwargs):
        seen["preflight"] = kwargs

    def fake_build_main_stream(hex_mem):
        seen["stream_hex_mem"] = dict(hex_mem)
        return b"STREAM"

    def fake_flash_main(**kwargs):
        seen["flash_kwargs"] = kwargs
        return SimpleNamespace(path=b"/fake/hid")

    class FakeDev:
        def close(self) -> None:
            return None

    def fake_write_slot(dev, *, name_slot):
        seen["written_slot"] = name_slot
        return name_slot

    def fake_read_slot(dev):
        seen["read_back"] = True
        return name_slot

    def fake_read_flash_window(**kwargs):
        seen["read_window_kwargs"] = kwargs
        return table

    def fake_apply_routes(**kwargs):
        seen["route_kwargs"] = kwargs
        return (
            RouteEntry(channel=1, value=0, label="L"),
            RouteEntry(channel=2, value=0, label="L"),
        )

    monkeypatch.setattr(hw, "parse_intel_hex", fake_parse_intel_hex)
    monkeypatch.setattr(hw, "run_preflight", fake_run_preflight)
    monkeypatch.setattr(hw, "build_main_stream", fake_build_main_stream)
    monkeypatch.setattr(hw, "flash_main", fake_flash_main)
    monkeypatch.setattr(hw, "_open_hid", lambda path: FakeDev())
    monkeypatch.setattr(hw, "_cmd03_write_filename_slot", fake_write_slot)
    monkeypatch.setattr(hw, "_cmd03_read_filename_slot", fake_read_slot)
    monkeypatch.setattr(hw, "read_flash_window", fake_read_flash_window)
    monkeypatch.setattr(hw, "_apply_all_channel_mapping", fake_apply_routes)

    result = hw._flash_and_finalize(
        flashed_hex=flashed_hex,
        overlay_a=overlay,
        route="L",
        vid=0x04D8,
        pid=0xFF89,
        verbose=False,
    )

    assert seen["flash_kwargs"]["stream"] == b"STREAM"
    assert seen["flash_kwargs"]["need_post_app"] is True
    assert seen["written_slot"] == name_slot
    assert seen["read_back"] is True
    assert seen["read_window_kwargs"]["start"] == PRESET_A_FLASH_BASE
    assert seen["route_kwargs"]["route_label"] == "L"
    assert result["config_name"] == "ALPHA-A"
    assert result["preset_a_sha256"] == hashlib.sha256(table).hexdigest()
    assert result["routes"] == [
        {"channel": 1, "value": 0, "label": "L"},
        {"channel": 2, "value": 0, "label": "L"},
    ]


def test_run_once_with_flash_path_copies_baked_firmware_artifacts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    base_hex = tmp_path / "base.hex"
    write_intel_hex(base_hex, {0x1000: 0x11})
    capture, sidecar, table, name_slot = _write_capture_a_fixture(tmp_path)
    seen: dict[str, object] = {}

    def fake_flash_and_finalize(**kwargs):
        overlay = kwargs["overlay_a"]
        seen["flash_overlay"] = overlay
        return {
            "config_name": overlay.config_name,
            "preset_a_sha256": hashlib.sha256(overlay.table).hexdigest(),
        }

    def fake_capture_and_play_verified(**kwargs):
        seen["capture_args"] = kwargs
        kwargs["capture_path"].write_bytes(b"capture")
        return kwargs["capture_lead_s"], 2.5

    def fake_analyze_capture(**kwargs):
        out_dir = kwargs["out_dir"]
        metrics_path = out_dir / "metrics.json"
        csv_path = out_dir / "response_mag.csv"
        metrics = {
            "classification": "VALID_NO_BASELINE",
            "decision": "GO",
            "snr_db": 24.0,
        }
        metrics_path.write_text(json.dumps(metrics), encoding="ascii")
        csv_path.write_text("freq_hz,mag_db\n100,0\n", encoding="ascii")
        return SimpleNamespace(
            metrics_path=metrics_path,
            response_mag_csv_path=csv_path,
            response_mag_png_path=None,
            metrics=metrics,
        )

    monkeypatch.setattr(hw, "_flash_and_finalize", fake_flash_and_finalize)
    monkeypatch.setattr(hw, "_capture_and_play_verified", fake_capture_and_play_verified)
    monkeypatch.setattr(hw, "analyze_capture", fake_analyze_capture)

    summary = hw._run_once(
        run_dir=run_dir,
        base_hex=base_hex,
        capture_a=capture,
        meta_a=sidecar,
        name_a=None,
        route="L",
        input_device="UMIK-2",
        output_device="USB Audio DAC",
        stimulus_path=None,
        stimulus_manifest=None,
        sweep_spec=hw.SweepSpec(
            sample_rate=48_000,
            start_hz=20.0,
            end_hz=20_000.0,
            sweep_s=0.2,
            pre_s=0.05,
            post_s=0.05,
            amplitude=0.2,
            channels=2,
            fade_s=0.01,
        ),
        capture_sample_rate=48_000,
        capture_channels=2,
        capture_lead_s=0.25,
        baseline_csv=None,
        compare_min_hz=None,
        compare_max_hz=None,
        vid=0x04D8,
        pid=0xFF89,
        verbose=False,
    )

    assert seen["flash_overlay"].config_name == "ALPHA-A"
    assert seen["flash_overlay"].name_slot == name_slot
    assert bytes(seen["flash_overlay"].table[:0x20]) == table[:0x20]
    assert (run_dir / "firmware.hex").exists()
    assert (run_dir / "firmware.json").exists()
    copied_mem = parse_intel_hex(run_dir / "firmware.hex")
    assert bytes(copied_mem.get(PRESET_A_FLASH_BASE + i, 0xFF) for i in range(0x20)) == table[:0x20]
    assert summary["firmware"]["config_name"] == "ALPHA-A"
    assert summary["classification"] == "VALID_NO_BASELINE"


def test_analyze_capture_without_baseline_produces_valid_metrics(tmp_path: Path) -> None:
    stimulus = tmp_path / "stimulus.wav"
    spec = hw.SweepSpec(
        sample_rate=48_000,
        start_hz=20.0,
        end_hz=20_000.0,
        sweep_s=1.0,
        pre_s=0.1,
        post_s=0.1,
        amplitude=0.2,
        channels=2,
    )
    manifest = hw._write_sweep(stimulus, spec)
    manifest_path = tmp_path / "stimulus.json"
    manifest_path.write_text(json.dumps(hw.dataclasses.asdict(manifest)), encoding="ascii")

    rate, stim = hw._read_wav(stimulus)
    stim_mono = hw._channel_select(stim, "mix")

    lead = int(round(0.25 * rate))
    ir = np.zeros(512, dtype=np.float64)
    ir[123] = 0.7
    ir[160] = 0.2
    convolved = np.convolve(stim_mono, ir)
    capture = np.concatenate([np.zeros(lead, dtype=np.float64), convolved, np.zeros(rate // 8)])
    capture_path = tmp_path / "capture.wav"
    hw._write_wav(capture_path, rate, np.repeat(capture[:, None], 2, axis=1))

    result = hw.analyze_capture(
        stimulus_path=stimulus,
        capture_path=capture_path,
        out_dir=tmp_path / "analysis",
        channel_mode="mix",
        baseline_csv=None,
        manifest_path=manifest_path,
        capture_lead_s=0.25,
        compare_min_hz=100.0,
        compare_max_hz=10_000.0,
        title="synthetic",
    )
    assert result.metrics["classification"] == "VALID_NO_BASELINE"
    assert result.metrics["decision"] == "GO"
    assert float(result.metrics["snr_db"]) > 10.0
    got_lag = int(result.metrics["ir_peak_index"])
    assert abs(got_lag - (lead + 123)) <= 3
    assert result.response_mag_csv_path.exists()
    assert result.metrics_path.exists()


def test_analyze_capture_classifies_low_level_against_baseline(tmp_path: Path) -> None:
    stimulus = tmp_path / "stimulus.wav"
    spec = hw.SweepSpec(
        sample_rate=48_000,
        start_hz=20.0,
        end_hz=20_000.0,
        sweep_s=1.0,
        pre_s=0.1,
        post_s=0.1,
        amplitude=0.2,
        channels=2,
    )
    manifest = hw._write_sweep(stimulus, spec)
    manifest_path = tmp_path / "stimulus.json"
    manifest_path.write_text(json.dumps(hw.dataclasses.asdict(manifest)), encoding="ascii")
    rate, stim = hw._read_wav(stimulus)
    stim_mono = hw._channel_select(stim, "mix")
    lead = int(round(0.25 * rate))

    ir = np.zeros(512, dtype=np.float64)
    ir[80] = 0.8
    ir[140] = 0.15
    base_capture = np.concatenate(
        [np.zeros(lead, dtype=np.float64), np.convolve(stim_mono, ir), np.zeros(rate // 8)]
    )
    cand_capture = base_capture * 0.1

    base_path = tmp_path / "baseline_capture.wav"
    cand_path = tmp_path / "candidate_capture.wav"
    hw._write_wav(base_path, rate, np.repeat(base_capture[:, None], 2, axis=1))
    hw._write_wav(cand_path, rate, np.repeat(cand_capture[:, None], 2, axis=1))

    base_result = hw.analyze_capture(
        stimulus_path=stimulus,
        capture_path=base_path,
        out_dir=tmp_path / "baseline",
        channel_mode="mix",
        baseline_csv=None,
        manifest_path=manifest_path,
        capture_lead_s=0.25,
        compare_min_hz=100.0,
        compare_max_hz=10_000.0,
        title="baseline",
    )
    cand_result = hw.analyze_capture(
        stimulus_path=stimulus,
        capture_path=cand_path,
        out_dir=tmp_path / "candidate",
        channel_mode="mix",
        baseline_csv=base_result.response_mag_csv_path,
        manifest_path=manifest_path,
        capture_lead_s=0.25,
        compare_min_hz=100.0,
        compare_max_hz=10_000.0,
        title="candidate",
    )
    assert cand_result.metrics["classification"] == "FAIL_LOW_LEVEL"
    assert cand_result.metrics["decision"] == "NOGO"
    assert float(cand_result.metrics["compare_mean_db"]) < -12.0


def test_capture_and_play_verified_retries_short_capture(monkeypatch, tmp_path: Path) -> None:
    stimulus = tmp_path / "stimulus.wav"
    spec = hw.SweepSpec(
        sample_rate=48_000,
        start_hz=120.0,
        end_hz=12_000.0,
        sweep_s=1.0,
        pre_s=0.5,
        post_s=1.0,
        amplitude=1.0,
        channels=2,
    )
    manifest = hw._write_sweep(stimulus, spec)
    capture_path = tmp_path / "capture.wav"
    attempts: list[tuple[float, float]] = []
    durations = iter([2.30, 2.60])

    def fake_capture_and_play(**kwargs) -> None:
        attempts.append((kwargs["capture_lead_s"], kwargs["capture_duration_s"]))
        duration_s = next(durations)
        samples = np.zeros((int(round(duration_s * 48_000)), 2), dtype=np.float64)
        hw._write_wav(kwargs["capture_path"], 48_000, samples)

    monkeypatch.setattr(hw, "_capture_and_play", fake_capture_and_play)
    lead_s, actual_s = hw._capture_and_play_verified(
        input_device="UMIK-2",
        output_device="USB Audio DAC",
        stimulus_path=stimulus,
        capture_path=capture_path,
        manifest=manifest,
        capture_sample_rate=48_000,
        capture_channels=2,
        capture_lead_s=0.25,
    )

    assert len(attempts) == 2
    assert attempts[0] == (0.25, 3.25)
    assert attempts[1] == (1.0, 4.0)
    assert lead_s == 1.0
    assert actual_s == 2.60


def test_capture_and_play_verified_raises_after_repeated_short_capture(
    monkeypatch,
    tmp_path: Path,
) -> None:
    stimulus = tmp_path / "stimulus.wav"
    spec = hw.SweepSpec(
        sample_rate=48_000,
        start_hz=120.0,
        end_hz=12_000.0,
        sweep_s=1.0,
        pre_s=0.5,
        post_s=1.0,
        amplitude=1.0,
        channels=2,
    )
    manifest = hw._write_sweep(stimulus, spec)
    capture_path = tmp_path / "capture.wav"

    def fake_capture_and_play(**kwargs) -> None:
        samples = np.zeros((int(round(1.4 * 48_000)), 2), dtype=np.float64)
        hw._write_wav(kwargs["capture_path"], 48_000, samples)

    monkeypatch.setattr(hw, "_capture_and_play", fake_capture_and_play)

    with pytest.raises(RuntimeError, match="shorter than required"):
        hw._capture_and_play_verified(
            input_device="UMIK-2",
            output_device="USB Audio DAC",
            stimulus_path=stimulus,
            capture_path=capture_path,
            manifest=manifest,
            capture_sample_rate=48_000,
            capture_channels=2,
            capture_lead_s=0.25,
        )


def test_resolve_compare_band_uses_manifest_defaults() -> None:
    manifest = hw.SweepManifest(
        format="dlcp_hardware_loop_sweep_v1",
        sample_rate=44_100,
        start_hz=120.0,
        end_hz=12_000.0,
        sweep_s=4.0,
        pre_s=0.5,
        post_s=1.0,
        total_s=5.5,
        amplitude=1.0,
        channels=2,
        fade_s=0.01,
        wav_path="stimulus.wav",
        wav_sha256="deadbeef",
    )
    compare_min_hz, compare_max_hz = hw._resolve_compare_band(
        manifest=manifest,
        compare_min_hz=None,
        compare_max_hz=None,
    )
    assert compare_min_hz == 120.0
    assert compare_max_hz == 12_000.0


def test_resolve_compare_band_prefers_explicit_over_manifest() -> None:
    manifest = hw.SweepManifest(
        format="dlcp_hardware_loop_sweep_v1",
        sample_rate=44_100,
        start_hz=120.0,
        end_hz=12_000.0,
        sweep_s=4.0,
        pre_s=0.5,
        post_s=1.0,
        total_s=5.5,
        amplitude=1.0,
        channels=2,
        fade_s=0.01,
        wav_path="stimulus.wav",
        wav_sha256="deadbeef",
    )
    compare_min_hz, compare_max_hz = hw._resolve_compare_band(
        manifest=manifest,
        compare_min_hz=200.0,
        compare_max_hz=8_000.0,
    )
    assert compare_min_hz == 200.0
    assert compare_max_hz == 8_000.0


def test_run_matrix_parser_exposes_compare_band_args() -> None:
    parser = hw.build_parser()

    args = parser.parse_args(
        [
            "run-matrix",
            "--hex",
            "firmware_a.hex",
            "--capture-a",
            "presetA.bin",
            "--compare-min-hz",
            "150",
            "--compare-max-hz",
            "9000",
        ]
    )

    assert args.compare_min_hz == 150.0
    assert args.compare_max_hz == 9000.0
