#!/usr/bin/env python3
"""Real-hardware DLCP playback/capture helpers for hardware-in-the-loop tests."""

from __future__ import annotations

import argparse
import contextlib
import csv
import dataclasses
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import wave
from typing import Iterable, Optional, Sequence

import numpy as np

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover - exercised only when PIL is missing
    Image = None
    ImageDraw = None
    ImageFont = None

from dlcp_fw.flash.dlcp_ep0_flash_probe import read_flash_window
from dlcp_fw.flash.dlcp_main_flash import (
    ALL_CH_ROUTE_VALUES,
    DEFAULT_PID,
    DEFAULT_VID,
    PRESET_A_FLASH_BASE,
    PRESET_TABLE_SIZE,
    _apply_all_channel_mapping,
    _cmd03_read_filename_slot,
    _cmd03_write_filename_slot,
    _load_capture_overlay,
    _open_hid,
    _pick_device,
    build_main_stream,
    decode_filename_slot,
    flash_main,
    parse_intel_hex,
    run_preflight,
)
from dlcp_fw.paths import ARTIFACTS_DIR, STOCK_MAIN_COMBINED_HEX


DEFAULT_INPUT_DEVICE = "UMIK-2"
DEFAULT_OUTPUT_DEVICE = "USB Audio DAC"
DEFAULT_CAPTURE_LEAD_S = 1.5
DEFAULT_MEASURE_ROOT = ARTIFACTS_DIR / "probes" / "hardware_loop"
DEFAULT_FW_ROOT = DEFAULT_MEASURE_ROOT / "fw"
DEFAULT_RUNS_ROOT = DEFAULT_MEASURE_ROOT / "runs"
DEFAULT_SWEEP_SR = 48_000
DEFAULT_SWEEP_START_HZ = 20.0
DEFAULT_SWEEP_END_HZ = 20_000.0
DEFAULT_SWEEP_LEN_S = 4.0
DEFAULT_PRE_S = 0.5
DEFAULT_POST_S = 1.0
DEFAULT_SWEEP_AMPLITUDE = 0.2
DEFAULT_CAPTURE_CHANNELS = 2
DEFAULT_ANALYZE_CHANNEL = "mix"
DEFAULT_COMPARE_MIN_HZ = 100.0
DEFAULT_COMPARE_MAX_HZ = 10_000.0
CAPTURE_TAIL_PAD_S = 0.5
CAPTURE_MIN_REQUIRED_LEAD_S = 0.25
CAPTURE_MIN_DURATION_TOLERANCE_S = 0.2
CAPTURE_RETRY_LIMIT = 3
CAPTURE_RETRY_LEAD_STEP_S = 0.75

PASS_MATCH_RMS_DB = 3.0
PASS_NEAR_RMS_DB = 6.0
LOW_LEVEL_MEAN_DB = -12.0
MIN_VALID_SNR_DB = 10.0
CLIP_THRESHOLD = 0.999

_AVF_AUDIO_RE = re.compile(r"\[(\d+)\]\s+(.*)$")


def _decision_from_classification(classification: str) -> str:
    if classification in ("VALID_NO_BASELINE", "PASS_MATCHES_BASELINE", "PASS_NEAR_BASELINE"):
        return "GO"
    return "NOGO"


@dataclasses.dataclass(frozen=True)
class AudioInputDevice:
    name: str
    avfoundation_index: int


@dataclasses.dataclass(frozen=True)
class AudioSystemDevice:
    name: str
    input_channels: int
    output_channels: int
    sample_rate: int
    manufacturer: str
    transport: str
    is_default_input: bool
    is_default_output: bool
    avfoundation_index: Optional[int] = None


@dataclasses.dataclass(frozen=True)
class HidDeviceSummary:
    mode: str
    product: str
    manufacturer: str
    serial: str
    path: str


@dataclasses.dataclass(frozen=True)
class SweepSpec:
    sample_rate: int
    start_hz: float
    end_hz: float
    sweep_s: float
    pre_s: float
    post_s: float
    amplitude: float
    channels: int
    fade_s: float = 0.01

    @property
    def total_s(self) -> float:
        return self.pre_s + self.sweep_s + self.post_s


@dataclasses.dataclass(frozen=True)
class SweepManifest:
    format: str
    sample_rate: int
    start_hz: float
    end_hz: float
    sweep_s: float
    pre_s: float
    post_s: float
    total_s: float
    amplitude: float
    channels: int
    fade_s: float
    wav_path: str
    wav_sha256: str


@dataclasses.dataclass(frozen=True)
class MagnitudeTrace:
    freq_hz: np.ndarray
    mag_db: np.ndarray


@dataclasses.dataclass(frozen=True)
class AnalysisResult:
    sample_rate: int
    stimulus_path: Path
    capture_path: Path
    response_ir_path: Path
    response_mag_csv_path: Path
    response_mag_png_path: Optional[Path]
    metrics_path: Path
    response_trace: MagnitudeTrace
    metrics: dict[str, object]


@dataclasses.dataclass(frozen=True)
class FlashPreparation:
    base_hex: Path
    flashed_hex: Path
    flashed_manifest: Path
    config_name: str
    table_sha256: str


def _json_dumps(data: object) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _run(
    args: Sequence[str],
    *,
    check: bool = True,
    capture_output: bool = True,
    text: bool = True,
    env: Optional[dict[str, str]] = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        check=check,
        capture_output=capture_output,
        text=text,
        env=env,
    )


def _require_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(f"required tool not found on PATH: {name}")
    return path


def _slug(s: str) -> str:
    out = []
    for ch in s:
        if ch.isalnum():
            out.append(ch.lower())
        elif ch in ("-", "_", "."):
            out.append(ch)
        else:
            out.append("_")
    text = "".join(out).strip("._")
    return text or "run"


def _timestamp_now() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _load_system_audio_devices() -> list[AudioSystemDevice]:
    proc = _run(["system_profiler", "-json", "SPAudioDataType"])
    raw = json.loads(proc.stdout)
    groups = raw.get("SPAudioDataType", [])
    if not groups:
        return []
    items = groups[0].get("_items", [])
    out: list[AudioSystemDevice] = []
    for item in items:
        out.append(
            AudioSystemDevice(
                name=str(item.get("_name", "")),
                input_channels=int(item.get("coreaudio_device_input", 0) or 0),
                output_channels=int(item.get("coreaudio_device_output", 0) or 0),
                sample_rate=int(item.get("coreaudio_device_srate", 0) or 0),
                manufacturer=str(item.get("coreaudio_device_manufacturer", "")),
                transport=str(item.get("coreaudio_device_transport", "")),
                is_default_input="coreaudio_default_audio_input_device" in item,
                is_default_output="coreaudio_default_audio_output_device" in item
                or "coreaudio_default_audio_system_device" in item,
            )
        )
    return out


def _load_avfoundation_audio_inputs() -> list[AudioInputDevice]:
    proc = _run(
        ["ffmpeg", "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        check=False,
    )
    text = proc.stdout + proc.stderr
    out: list[AudioInputDevice] = []
    in_audio = False
    for line in text.splitlines():
        if "AVFoundation audio devices:" in line:
            in_audio = True
            continue
        if not in_audio:
            continue
        m = _AVF_AUDIO_RE.search(line)
        if m is None:
            continue
        out.append(AudioInputDevice(name=m.group(2).strip(), avfoundation_index=int(m.group(1))))
    return out


def _current_audio_device(kind: str) -> str:
    proc = _run(["SwitchAudioSource", "-c", "-t", kind])
    return proc.stdout.strip()


def _list_switch_audio(kind: str) -> list[str]:
    proc = _run(["SwitchAudioSource", "-a", "-t", kind])
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _combine_audio_inventory() -> list[AudioSystemDevice]:
    sys_devices = {dev.name: dev for dev in _load_system_audio_devices()}
    av_inputs = {dev.name: dev.avfoundation_index for dev in _load_avfoundation_audio_inputs()}
    names = set(sys_devices) | set(av_inputs)
    out: list[AudioSystemDevice] = []
    for name in sorted(names):
        base = sys_devices.get(name)
        if base is None:
            out.append(
                AudioSystemDevice(
                    name=name,
                    input_channels=1,
                    output_channels=0,
                    sample_rate=0,
                    manufacturer="",
                    transport="",
                    is_default_input=False,
                    is_default_output=False,
                    avfoundation_index=av_inputs.get(name),
                )
            )
        else:
            out.append(
                AudioSystemDevice(
                    name=base.name,
                    input_channels=base.input_channels,
                    output_channels=base.output_channels,
                    sample_rate=base.sample_rate,
                    manufacturer=base.manufacturer,
                    transport=base.transport,
                    is_default_input=base.is_default_input,
                    is_default_output=base.is_default_output,
                    avfoundation_index=av_inputs.get(name),
                )
            )
    return out


def _match_name(candidates: Iterable[str], wanted: str) -> str:
    names = list(candidates)
    if wanted in names:
        return wanted
    low = wanted.lower()
    exact_low = [name for name in names if name.lower() == low]
    if len(exact_low) == 1:
        return exact_low[0]
    partial = [name for name in names if low in name.lower()]
    if len(partial) == 1:
        return partial[0]
    choices = ", ".join(sorted(names)) if names else "<none>"
    raise RuntimeError(f"unable to resolve device {wanted!r}; choices: {choices}")


def _resolve_input_index(name: str) -> int:
    inputs = _load_avfoundation_audio_inputs()
    match = _match_name([dev.name for dev in inputs], name)
    for dev in inputs:
        if dev.name == match:
            return dev.avfoundation_index
    raise AssertionError("unreachable")


def _resolve_output_name(name: str) -> str:
    return _match_name(_list_switch_audio("output"), name)


def _resolve_input_name(name: str) -> str:
    return _match_name(_list_switch_audio("input"), name)


def _list_hid_devices() -> list[HidDeviceSummary]:
    try:
        from dlcp_fw.flash.dlcp_control_flash import enumerate_devices
        from dlcp_fw.flash.dlcp_main_flash import _device_mode
    except Exception:
        return []

    out: list[HidDeviceSummary] = []
    for dev in enumerate_devices(DEFAULT_VID, DEFAULT_PID):
        path = ""
        if dev.path is not None:
            path = dev.path.decode("utf-8", errors="replace")
        out.append(
            HidDeviceSummary(
                mode=_device_mode(dev),
                product=dev.product_string or "",
                manufacturer=dev.manufacturer_string or "",
                serial=dev.serial_number or "",
                path=path,
            )
        )
    return out


@contextlib.contextmanager
def _temporary_output_device(name: str):
    wanted = _resolve_output_name(name)
    previous = _current_audio_device("output")
    _run(["SwitchAudioSource", "-s", wanted, "-t", "output"])
    try:
        yield wanted
    finally:
        _run(["SwitchAudioSource", "-s", previous, "-t", "output"])


def _write_wav(path: Path, sample_rate: int, samples: np.ndarray) -> None:
    arr = np.asarray(samples, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr[:, None]
    if arr.ndim != 2:
        raise ValueError("samples must be 1D or 2D")
    clipped = np.clip(arr, -1.0, 1.0)
    pcm = np.round(clipped * 32767.0).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(int(pcm.shape[1]))
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.reshape(-1).tobytes())


def _read_wav(path: Path) -> tuple[int, np.ndarray]:
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        sampwidth = wf.getsampwidth()
        frames = wf.getnframes()
        raw = wf.readframes(frames)
    if sampwidth != 2:
        raise RuntimeError(f"{path} uses unsupported sample width {sampwidth}; expected 16-bit PCM")
    data = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels)
    return sample_rate, data


def _channel_select(data: np.ndarray, mode: str) -> np.ndarray:
    arr = np.asarray(data, dtype=np.float64)
    if arr.ndim == 1:
        return arr
    if arr.ndim != 2:
        raise ValueError("audio array must be 1D or 2D")
    mode_low = mode.lower()
    if mode_low in ("mix", "avg", "mean"):
        return arr.mean(axis=1)
    if mode_low in ("left", "l", "0"):
        return arr[:, 0]
    if mode_low in ("right", "r", "1"):
        if arr.shape[1] < 2:
            return arr[:, 0]
        return arr[:, 1]
    raise ValueError(f"unsupported channel mode: {mode}")


def _resample_linear(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate:
        return np.asarray(samples, dtype=np.float64)
    if len(samples) == 0:
        return np.asarray(samples, dtype=np.float64)
    duration = len(samples) / float(src_rate)
    out_len = max(1, int(round(duration * dst_rate)))
    src_t = np.linspace(0.0, duration, num=len(samples), endpoint=False)
    dst_t = np.linspace(0.0, duration, num=out_len, endpoint=False)
    return np.interp(dst_t, src_t, samples).astype(np.float64)


def _rms_dbfs(samples: np.ndarray) -> float:
    arr = np.asarray(samples, dtype=np.float64)
    if len(arr) == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(arr * arr)))
    return 20.0 * math.log10(max(rms, 1e-12))


def _peak_dbfs(samples: np.ndarray) -> float:
    arr = np.asarray(samples, dtype=np.float64)
    if len(arr) == 0:
        return -120.0
    peak = float(np.max(np.abs(arr)))
    return 20.0 * math.log10(max(peak, 1e-12))


def _moving_average(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return values
    kernel = np.ones(window, dtype=np.float64) / float(window)
    return np.convolve(values, kernel, mode="same")


def _next_pow2(n: int) -> int:
    return 1 << max(1, int(math.ceil(math.log2(max(2, n)))))


def _log_grid_trace(freq_hz: np.ndarray, mag_db: np.ndarray, *, points: int = 512) -> MagnitudeTrace:
    valid = freq_hz > 0
    freq = freq_hz[valid]
    mag = mag_db[valid]
    grid = np.geomspace(20.0, min(20_000.0, float(freq[-1])), num=points)
    interp = np.interp(np.log(grid), np.log(freq), mag).astype(np.float64)
    smooth = _moving_average(interp, 9)
    return MagnitudeTrace(freq_hz=grid, mag_db=smooth)


def _write_trace_csv(path: Path, trace: MagnitudeTrace, *, baseline: Optional[MagnitudeTrace] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="") as fh:
        writer = csv.writer(fh)
        if baseline is None:
            writer.writerow(["freq_hz", "mag_db"])
            for f_hz, mag_db in zip(trace.freq_hz, trace.mag_db):
                writer.writerow([f"{f_hz:.6f}", f"{mag_db:.6f}"])
            return

        base_interp = np.interp(
            np.log(trace.freq_hz),
            np.log(baseline.freq_hz),
            baseline.mag_db,
        )
        writer.writerow(["freq_hz", "mag_db", "baseline_mag_db", "diff_db"])
        for f_hz, mag_db, base_db in zip(trace.freq_hz, trace.mag_db, base_interp):
            writer.writerow(
                [
                    f"{f_hz:.6f}",
                    f"{mag_db:.6f}",
                    f"{base_db:.6f}",
                    f"{(mag_db - base_db):.6f}",
                ]
            )


def _read_trace_csv(path: Path) -> MagnitudeTrace:
    freq: list[float] = []
    mag: list[float] = []
    with path.open("r", encoding="ascii", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            freq.append(float(row["freq_hz"]))
            mag.append(float(row["mag_db"]))
    return MagnitudeTrace(freq_hz=np.asarray(freq, dtype=np.float64), mag_db=np.asarray(mag, dtype=np.float64))


def _write_trace_png(
    path: Path,
    trace: MagnitudeTrace,
    *,
    baseline: Optional[MagnitudeTrace],
    title: str,
    subtitle: str,
) -> Optional[Path]:
    if Image is None:
        return None

    width = 1280
    height = 720
    margin_l = 90
    margin_r = 30
    margin_t = 60
    margin_b = 70
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b

    base_interp = None
    ymin = float(np.min(trace.mag_db))
    ymax = float(np.max(trace.mag_db))
    if baseline is not None:
        base_interp = np.interp(np.log(trace.freq_hz), np.log(baseline.freq_hz), baseline.mag_db)
        ymin = min(ymin, float(np.min(base_interp)))
        ymax = max(ymax, float(np.max(base_interp)))
    ymin = math.floor((ymin - 6.0) / 6.0) * 6.0
    ymax = math.ceil((ymax + 6.0) / 6.0) * 6.0
    if ymax <= ymin:
        ymax = ymin + 12.0

    img = Image.new("RGB", (width, height), (250, 250, 250))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    draw.rectangle((margin_l, margin_t, margin_l + plot_w, margin_t + plot_h), outline=(0, 0, 0), width=1)
    draw.text((margin_l, 12), title, fill=(0, 0, 0), font=font)
    draw.text((margin_l, 30), subtitle, fill=(60, 60, 60), font=font)

    x_ticks = [20, 50, 100, 200, 500, 1_000, 2_000, 5_000, 10_000, 20_000]
    y_ticks = list(range(int(ymin), int(ymax) + 1, 6))

    def x_map(freq: float) -> float:
        lo = math.log10(20.0)
        hi = math.log10(20_000.0)
        pos = (math.log10(max(20.0, min(20_000.0, freq))) - lo) / (hi - lo)
        return margin_l + pos * plot_w

    def y_map(db: float) -> float:
        pos = (db - ymin) / (ymax - ymin)
        return margin_t + plot_h - pos * plot_h

    for tick in x_ticks:
        x = x_map(float(tick))
        draw.line((x, margin_t, x, margin_t + plot_h), fill=(225, 225, 225))
        label = f"{tick/1000:.0f}k" if tick >= 1000 else str(tick)
        draw.text((x - 10, margin_t + plot_h + 8), label, fill=(0, 0, 0), font=font)

    for tick in y_ticks:
        y = y_map(float(tick))
        draw.line((margin_l, y, margin_l + plot_w, y), fill=(235, 235, 235))
        draw.text((8, y - 6), f"{tick}", fill=(0, 0, 0), font=font)

    def draw_trace(freq: np.ndarray, mag: np.ndarray, color: tuple[int, int, int]) -> None:
        pts: list[tuple[float, float]] = []
        for f_hz, mag_db in zip(freq, mag):
            pts.append((x_map(float(f_hz)), y_map(float(mag_db))))
        if len(pts) >= 2:
            draw.line(pts, fill=color, width=2)

    if base_interp is not None:
        draw_trace(trace.freq_hz, base_interp, (140, 140, 140))
        draw.text((margin_l + 8, margin_t + 8), "baseline", fill=(140, 140, 140), font=font)
    draw_trace(trace.freq_hz, trace.mag_db, (30, 110, 30))
    draw.text((margin_l + 70, margin_t + 8), "candidate", fill=(30, 110, 30), font=font)

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def _generate_log_sweep(spec: SweepSpec) -> np.ndarray:
    if spec.sample_rate <= 0:
        raise ValueError("sample_rate must be > 0")
    if spec.start_hz <= 0 or spec.end_hz <= spec.start_hz:
        raise ValueError("invalid sweep frequency range")
    if spec.sweep_s <= 0:
        raise ValueError("sweep_s must be > 0")
    samples = int(round(spec.sweep_s * spec.sample_rate))
    t = np.arange(samples, dtype=np.float64) / float(spec.sample_rate)
    ratio = spec.end_hz / spec.start_hz
    k = spec.sweep_s / math.log(ratio)
    phase = 2.0 * math.pi * spec.start_hz * k * (np.exp(t / k) - 1.0)
    sweep = np.sin(phase)

    fade_n = max(1, int(round(spec.fade_s * spec.sample_rate)))
    fade_n = min(fade_n, len(sweep) // 2)
    if fade_n > 0:
        ramp = 0.5 - 0.5 * np.cos(np.linspace(0.0, math.pi, num=fade_n, endpoint=True))
        sweep[:fade_n] *= ramp
        sweep[-fade_n:] *= ramp[::-1]

    pre = np.zeros(int(round(spec.pre_s * spec.sample_rate)), dtype=np.float64)
    post = np.zeros(int(round(spec.post_s * spec.sample_rate)), dtype=np.float64)
    mono = np.concatenate([pre, sweep * spec.amplitude, post])
    if spec.channels == 1:
        return mono
    return np.repeat(mono[:, None], spec.channels, axis=1)


def _write_sweep(path: Path, spec: SweepSpec) -> SweepManifest:
    samples = _generate_log_sweep(spec)
    _write_wav(path, spec.sample_rate, samples)
    return SweepManifest(
        format="dlcp_hardware_loop_sweep_v1",
        sample_rate=spec.sample_rate,
        start_hz=spec.start_hz,
        end_hz=spec.end_hz,
        sweep_s=spec.sweep_s,
        pre_s=spec.pre_s,
        post_s=spec.post_s,
        total_s=spec.total_s,
        amplitude=spec.amplitude,
        channels=spec.channels,
        fade_s=spec.fade_s,
        wav_path=str(path),
        wav_sha256=_sha256_file(path),
    )


def _write_manifest(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_dumps(data), encoding="ascii")


def _load_manifest(path: Path) -> SweepManifest:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return SweepManifest(**raw)


def _capture_audio(
    *,
    input_device: str,
    duration_s: float,
    sample_rate: int,
    channels: int,
    out_path: Path,
) -> None:
    idx = _resolve_input_index(input_device)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-f",
            "avfoundation",
            "-t",
            f"{duration_s:.3f}",
            "-i",
            f":{idx}",
            "-ac",
            str(channels),
            "-ar",
            str(sample_rate),
            str(out_path),
        ]
    )


def _wav_duration_s(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        sample_rate = handle.getframerate()
        frames = handle.getnframes()
    if sample_rate <= 0:
        raise RuntimeError(f"{path} has invalid sample rate {sample_rate}")
    return frames / float(sample_rate)


def _play_audio(*, output_device: str, wav_path: Path) -> None:
    with _temporary_output_device(output_device):
        _run(["afplay", str(wav_path)])


def _capture_and_play(
    *,
    input_device: str,
    output_device: str,
    stimulus_path: Path,
    capture_path: Path,
    capture_duration_s: float,
    capture_sample_rate: int,
    capture_channels: int,
    capture_lead_s: float,
) -> None:
    idx = _resolve_input_index(input_device)
    capture_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-f",
        "avfoundation",
        "-t",
        f"{capture_duration_s:.3f}",
        "-i",
        f":{idx}",
        "-ac",
        str(capture_channels),
        "-ar",
        str(capture_sample_rate),
        str(capture_path),
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        time.sleep(max(0.0, capture_lead_s))
        with _temporary_output_device(output_device):
            _run(["afplay", str(stimulus_path)])
        stdout, stderr = proc.communicate(timeout=max(5.0, capture_duration_s + 5.0))
        if proc.returncode != 0:
            raise RuntimeError(
                "ffmpeg capture failed during run-once:\n"
                f"stdout:\n{stdout}\n\nstderr:\n{stderr}"
            )
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()


def _minimum_capture_duration_s(*, manifest: SweepManifest, capture_lead_s: float) -> float:
    required_lead_s = min(capture_lead_s, CAPTURE_MIN_REQUIRED_LEAD_S)
    return manifest.total_s + required_lead_s


def _resolve_compare_band(
    *,
    manifest: Optional[SweepManifest],
    compare_min_hz: Optional[float],
    compare_max_hz: Optional[float],
) -> tuple[float, float]:
    resolved_min = compare_min_hz
    resolved_max = compare_max_hz
    if manifest is not None:
        if resolved_min is None:
            resolved_min = manifest.start_hz
        if resolved_max is None:
            resolved_max = manifest.end_hz
    if resolved_min is None:
        resolved_min = DEFAULT_COMPARE_MIN_HZ
    if resolved_max is None:
        resolved_max = DEFAULT_COMPARE_MAX_HZ
    if resolved_min <= 0.0 or resolved_max <= 0.0:
        raise RuntimeError(
            f"invalid compare band {resolved_min}..{resolved_max} Hz; frequencies must be positive"
        )
    if resolved_max < resolved_min:
        raise RuntimeError(
            f"invalid compare band {resolved_min}..{resolved_max} Hz; max must be >= min"
        )
    return float(resolved_min), float(resolved_max)


def _capture_and_play_verified(
    *,
    input_device: str,
    output_device: str,
    stimulus_path: Path,
    capture_path: Path,
    manifest: SweepManifest,
    capture_sample_rate: int,
    capture_channels: int,
    capture_lead_s: float,
) -> tuple[float, float]:
    lead_s = capture_lead_s
    last_actual_s: Optional[float] = None
    last_required_s: Optional[float] = None
    for attempt in range(1, CAPTURE_RETRY_LIMIT + 1):
        capture_duration_s = manifest.total_s + lead_s + CAPTURE_TAIL_PAD_S
        _capture_and_play(
            input_device=input_device,
            output_device=output_device,
            stimulus_path=stimulus_path,
            capture_path=capture_path,
            capture_duration_s=capture_duration_s,
            capture_sample_rate=capture_sample_rate,
            capture_channels=capture_channels,
            capture_lead_s=lead_s,
        )
        actual_s = _wav_duration_s(capture_path)
        required_s = _minimum_capture_duration_s(manifest=manifest, capture_lead_s=lead_s)
        last_actual_s = actual_s
        last_required_s = required_s
        if actual_s + CAPTURE_MIN_DURATION_TOLERANCE_S >= required_s:
            return lead_s, actual_s
        if attempt == CAPTURE_RETRY_LIMIT:
            break
        lead_s += CAPTURE_RETRY_LEAD_STEP_S
    raise RuntimeError(
        "capture.wav was shorter than required for a valid sweep window after "
        f"{CAPTURE_RETRY_LIMIT} attempts: got {last_actual_s:.3f}s, "
        f"needed at least {last_required_s:.3f}s (tolerance {CAPTURE_MIN_DURATION_TOLERANCE_S:.3f}s)"
    )


def _prepare_flash_hex(
    *,
    base_hex: Path,
    capture_a: Optional[Path],
    meta_a: Optional[Path],
    name_a: Optional[str],
    out_dir: Path,
) -> tuple[Path, Path, Optional[object]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    hex_mem = parse_intel_hex(str(base_hex))
    overlay = None
    if capture_a is not None:
        overlay = _load_capture_overlay(
            capture_path=capture_a,
            explicit_meta=meta_a,
            name_override=name_a,
            preset="A",
        )
        for idx, value in enumerate(overlay.table):
            hex_mem[overlay.flash_base + idx] = value & 0xFF

    flashed_hex = out_dir / (base_hex.stem + ("_presetA" if overlay is not None else "") + ".hex")
    from dlcp_fw.sim.hexio import write_intel_hex

    write_intel_hex(flashed_hex, hex_mem)
    manifest_path = flashed_hex.with_suffix(".json")
    manifest: dict[str, object] = {
        "base_hex": str(base_hex),
        "flashed_hex": str(flashed_hex),
    }
    if overlay is not None:
        manifest["preset_a"] = {
            "capture": str(capture_a),
            "config_name": overlay.config_name,
            "table_sha256": _sha256_bytes(overlay.table),
            "flash_base": PRESET_A_FLASH_BASE,
        }
    _write_manifest(manifest_path, manifest)
    return flashed_hex, manifest_path, overlay


def _flash_and_finalize(
    *,
    flashed_hex: Path,
    overlay_a,
    route: Optional[str],
    vid: int,
    pid: int,
    verbose: bool,
) -> dict[str, object]:
    hex_mem = parse_intel_hex(str(flashed_hex))
    ref_mem = parse_intel_hex(str(STOCK_MAIN_COMBINED_HEX))
    run_preflight(
        hex_mem=hex_mem,
        bootloader_ref_mem=ref_mem,
        require_bootloader_match=True,
    )
    stream = build_main_stream(hex_mem)
    post_dev = flash_main(
        vid=vid,
        pid=pid,
        path=None,
        stream=stream,
        pace_ms=20,
        reconnect_timeout_s=10.0,
        reconnect_settle_ms=500,
        verify=True,
        skip_switch=False,
        dry_run=False,
        report_info=True,
        need_post_app=True,
        post_info_timeout_s=10.0,
        verbose=verbose,
    )
    if post_dev is None or post_dev.path is None:
        raise RuntimeError("post-flash app reconnect failed")

    result: dict[str, object] = {
        "flashed_hex": str(flashed_hex),
    }
    if overlay_a is not None:
        dev = _open_hid(post_dev.path)
        try:
            live_slot = _cmd03_write_filename_slot(dev, name_slot=overlay_a.name_slot)
            verify_slot = _cmd03_read_filename_slot(dev)
        finally:
            dev.close()
        if verify_slot != overlay_a.name_slot:
            raise RuntimeError(
                "post-flash filename verify failed: "
                f"got {verify_slot.hex()}, expected {overlay_a.name_slot.hex()}"
            )
        table = read_flash_window(
            vid=vid,
            pid=pid,
            start=PRESET_A_FLASH_BASE,
            size=len(overlay_a.table),
            chunk=0xFF,
        )
        if table != overlay_a.table:
            raise RuntimeError("post-flash EP0 verify failed for preset A flash window")
        result["config_name"] = decode_filename_slot(live_slot)
        result["preset_a_sha256"] = _sha256_bytes(table)

    if route is not None:
        routes = _apply_all_channel_mapping(vid=vid, pid=pid, route_label=route)
        result["routes"] = [dataclasses.asdict(route_entry) for route_entry in routes]
    return result


def _analysis_band_metrics(
    trace: MagnitudeTrace,
    *,
    baseline: Optional[MagnitudeTrace],
    min_hz: float,
    max_hz: float,
) -> dict[str, float]:
    mask = (trace.freq_hz >= min_hz) & (trace.freq_hz <= max_hz)
    if not np.any(mask):
        return {"band_mean_db": float("nan")}
    metrics: dict[str, float] = {
        "band_mean_db": float(np.mean(trace.mag_db[mask])),
    }
    if baseline is not None:
        base_interp = np.interp(np.log(trace.freq_hz), np.log(baseline.freq_hz), baseline.mag_db)
        diff = trace.mag_db[mask] - base_interp[mask]
        metrics["compare_mean_db"] = float(np.mean(diff))
        metrics["compare_rms_db"] = float(np.sqrt(np.mean(diff * diff)))
        centered = diff - np.mean(diff)
        metrics["compare_shape_rms_db"] = float(np.sqrt(np.mean(centered * centered)))
    return metrics


def analyze_capture(
    *,
    stimulus_path: Path,
    capture_path: Path,
    out_dir: Path,
    channel_mode: str,
    baseline_csv: Optional[Path],
    manifest_path: Optional[Path],
    capture_lead_s: float,
    compare_min_hz: float,
    compare_max_hz: float,
    title: str,
) -> AnalysisResult:
    stim_rate, stim_raw = _read_wav(stimulus_path)
    cap_rate, cap_raw = _read_wav(capture_path)
    capture_duration_s = len(cap_raw) / float(cap_rate)
    stim = _channel_select(stim_raw, "mix")
    cap = _channel_select(cap_raw, channel_mode)
    if cap_rate != stim_rate:
        cap = _resample_linear(cap, cap_rate, stim_rate)
        cap_rate = stim_rate

    manifest = _load_manifest(manifest_path) if manifest_path is not None else None
    n = _next_pow2(len(stim) + len(cap))
    stim_fft = np.fft.rfft(stim, n=n)
    cap_fft = np.fft.rfft(cap, n=n)
    denom = np.abs(stim_fft) ** 2
    eps = max(1e-12, float(np.max(denom)) * 1e-6)
    ir = np.fft.irfft(cap_fft * np.conj(stim_fft) / (denom + eps), n=n).real

    ir_peak_idx = int(np.argmax(np.abs(ir)))
    ir_peak_abs = float(np.max(np.abs(ir)))

    seg_start = max(0, ir_peak_idx - int(round(0.01 * stim_rate)))
    seg_len = min(len(ir) - seg_start, max(8192, int(round(0.2 * stim_rate))))
    ir_seg = ir[seg_start : seg_start + seg_len]
    if len(ir_seg) < 32:
        raise RuntimeError("impulse response window too short to analyze")

    ir_window = np.hanning(len(ir_seg))
    resp_fft = np.fft.rfft(ir_seg * ir_window, n=16384)
    freq = np.fft.rfftfreq(16384, d=1.0 / stim_rate)
    mag_db = 20.0 * np.log10(np.maximum(np.abs(resp_fft), 1e-12))
    trace = _log_grid_trace(freq, mag_db)

    baseline = _read_trace_csv(baseline_csv) if baseline_csv is not None else None

    noise_len = max(1, int(round(0.25 * stim_rate)))
    noise = cap[: min(len(cap), noise_len)]
    if manifest is None:
        active_start = int(round(capture_lead_s * stim_rate))
        active_end = min(len(cap), active_start + len(stim))
    else:
        active_start = int(round((capture_lead_s + manifest.pre_s) * stim_rate))
        active_end = min(
            len(cap),
            int(round((capture_lead_s + manifest.pre_s + manifest.sweep_s + manifest.post_s) * stim_rate)),
        )
    signal = cap[active_start:active_end] if active_end > active_start else cap

    noise_rms_dbfs = _rms_dbfs(noise)
    signal_rms_dbfs = _rms_dbfs(signal)
    capture_peak_dbfs = _peak_dbfs(cap)
    snr_db = signal_rms_dbfs - noise_rms_dbfs
    clipped = bool(np.max(np.abs(cap)) >= CLIP_THRESHOLD)

    band_metrics = _analysis_band_metrics(
        trace,
        baseline=baseline,
        min_hz=compare_min_hz,
        max_hz=compare_max_hz,
    )

    classification = "VALID_NO_BASELINE"
    if clipped or snr_db < MIN_VALID_SNR_DB:
        classification = "FAIL_CAPTURE_INVALID"
    elif baseline is not None:
        rms_db = float(band_metrics.get("compare_rms_db", 999.0))
        mean_db = float(band_metrics.get("compare_mean_db", 0.0))
        if rms_db <= PASS_MATCH_RMS_DB and abs(mean_db) <= PASS_MATCH_RMS_DB:
            classification = "PASS_MATCHES_BASELINE"
        elif rms_db <= PASS_NEAR_RMS_DB and abs(mean_db) <= PASS_NEAR_RMS_DB:
            classification = "PASS_NEAR_BASELINE"
        elif mean_db <= LOW_LEVEL_MEAN_DB:
            classification = "FAIL_LOW_LEVEL"
        else:
            classification = "FAIL_SHAPE_MISMATCH"

    out_dir.mkdir(parents=True, exist_ok=True)
    ir_path = out_dir / "response_ir.wav"
    ir_norm = ir / max(1e-12, np.max(np.abs(ir)))
    _write_wav(ir_path, stim_rate, ir_norm.astype(np.float64))

    csv_path = out_dir / "response_mag.csv"
    _write_trace_csv(csv_path, trace, baseline=baseline)

    png_path = _write_trace_png(
        out_dir / "response_mag.png",
        trace,
        baseline=baseline,
        title=title,
        subtitle=f"classification={classification} snr_db={snr_db:.2f}",
    )

    metrics: dict[str, object] = {
        "format": "dlcp_hardware_loop_analysis_v1",
        "stimulus_path": str(stimulus_path),
        "capture_path": str(capture_path),
        "sample_rate": stim_rate,
        "channel_mode": channel_mode,
        "baseline_csv": str(baseline_csv) if baseline_csv is not None else None,
        "capture_peak_dbfs": capture_peak_dbfs,
        "capture_duration_s": capture_duration_s,
        "signal_rms_dbfs": signal_rms_dbfs,
        "noise_rms_dbfs": noise_rms_dbfs,
        "snr_db": snr_db,
        "ir_peak_index": ir_peak_idx,
        "ir_peak_seconds": ir_peak_idx / float(stim_rate),
        "ir_peak_abs": ir_peak_abs,
        "classification": classification,
        "decision": _decision_from_classification(classification),
        "clipped": clipped,
    }
    metrics.update(band_metrics)

    metrics_path = out_dir / "metrics.json"
    _write_manifest(metrics_path, metrics)
    return AnalysisResult(
        sample_rate=stim_rate,
        stimulus_path=stimulus_path,
        capture_path=capture_path,
        response_ir_path=ir_path,
        response_mag_csv_path=csv_path,
        response_mag_png_path=png_path,
        metrics_path=metrics_path,
        response_trace=trace,
        metrics=metrics,
    )


def _measure_root() -> Path:
    return DEFAULT_MEASURE_ROOT


def _run_dir(tag: str, root: Path) -> Path:
    return root / f"{_timestamp_now()}_{_slug(tag)}"


def _copy_into(path: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)
    return dst


def _run_once(
    *,
    run_dir: Path,
    base_hex: Optional[Path],
    capture_a: Optional[Path],
    meta_a: Optional[Path],
    name_a: Optional[str],
    route: Optional[str],
    input_device: str,
    output_device: str,
    stimulus_path: Optional[Path],
    stimulus_manifest: Optional[Path],
    sweep_spec: SweepSpec,
    capture_sample_rate: int,
    capture_channels: int,
    capture_lead_s: float,
    baseline_csv: Optional[Path],
    compare_min_hz: Optional[float],
    compare_max_hz: Optional[float],
    vid: int,
    pid: int,
    verbose: bool,
) -> dict[str, object]:
    run_dir.mkdir(parents=True, exist_ok=True)

    flash_summary: Optional[dict[str, object]] = None
    used_stimulus: Path
    used_manifest: Path

    if stimulus_path is None:
        used_stimulus = run_dir / "stimulus.wav"
        manifest = _write_sweep(used_stimulus, sweep_spec)
        used_manifest = run_dir / "stimulus.json"
        _write_manifest(used_manifest, dataclasses.asdict(manifest))
    else:
        used_stimulus = _copy_into(stimulus_path, run_dir / "stimulus.wav")
        if stimulus_manifest is not None:
            used_manifest = _copy_into(stimulus_manifest, run_dir / "stimulus.json")
        else:
            stim_rate, _ = _read_wav(used_stimulus)
            manifest = SweepManifest(
                format="dlcp_hardware_loop_sweep_v1",
                sample_rate=stim_rate,
                start_hz=DEFAULT_SWEEP_START_HZ,
                end_hz=DEFAULT_SWEEP_END_HZ,
                sweep_s=DEFAULT_SWEEP_LEN_S,
                pre_s=DEFAULT_PRE_S,
                post_s=DEFAULT_POST_S,
                total_s=DEFAULT_PRE_S + DEFAULT_SWEEP_LEN_S + DEFAULT_POST_S,
                amplitude=DEFAULT_SWEEP_AMPLITUDE,
                channels=2,
                fade_s=0.01,
                wav_path=str(used_stimulus),
                wav_sha256=_sha256_file(used_stimulus),
            )
            used_manifest = run_dir / "stimulus.json"
            _write_manifest(used_manifest, dataclasses.asdict(manifest))

    manifest = _load_manifest(used_manifest)
    resolved_compare_min_hz, resolved_compare_max_hz = _resolve_compare_band(
        manifest=manifest,
        compare_min_hz=compare_min_hz,
        compare_max_hz=compare_max_hz,
    )

    if base_hex is not None:
        fw_dir = run_dir / "fw"
        flashed_hex, flashed_manifest, overlay = _prepare_flash_hex(
            base_hex=base_hex,
            capture_a=capture_a,
            meta_a=meta_a,
            name_a=name_a,
            out_dir=fw_dir,
        )
        flash_summary = _flash_and_finalize(
            flashed_hex=flashed_hex,
            overlay_a=overlay,
            route=route,
            vid=vid,
            pid=pid,
            verbose=verbose,
        )
        _copy_into(flashed_hex, run_dir / "firmware.hex")
        _copy_into(flashed_manifest, run_dir / "firmware.json")

    capture_path = run_dir / "capture.wav"
    effective_capture_lead_s, actual_capture_duration_s = _capture_and_play_verified(
        input_device=input_device,
        output_device=output_device,
        stimulus_path=used_stimulus,
        capture_path=capture_path,
        manifest=manifest,
        capture_sample_rate=capture_sample_rate,
        capture_channels=capture_channels,
        capture_lead_s=capture_lead_s,
    )

    analysis = analyze_capture(
        stimulus_path=used_stimulus,
        capture_path=capture_path,
        out_dir=run_dir,
        channel_mode=DEFAULT_ANALYZE_CHANNEL,
        baseline_csv=baseline_csv,
        manifest_path=used_manifest,
        capture_lead_s=effective_capture_lead_s,
        compare_min_hz=resolved_compare_min_hz,
        compare_max_hz=resolved_compare_max_hz,
        title=run_dir.name,
    )
    notes = run_dir / "notes.txt"
    if not notes.exists():
        notes.write_text("", encoding="utf-8")

    summary = {
        "run_dir": str(run_dir),
        "firmware": flash_summary,
        "stimulus": str(used_stimulus),
        "capture": str(capture_path),
        "metrics": str(analysis.metrics_path),
        "response_mag_csv": str(analysis.response_mag_csv_path),
        "response_mag_png": str(analysis.response_mag_png_path) if analysis.response_mag_png_path else None,
        "classification": analysis.metrics["classification"],
        "decision": analysis.metrics["decision"],
        "snr_db": analysis.metrics["snr_db"],
        "capture_duration_s": actual_capture_duration_s,
        "effective_capture_lead_s": effective_capture_lead_s,
        "compare_min_hz": resolved_compare_min_hz,
        "compare_max_hz": resolved_compare_max_hz,
    }
    _write_manifest(run_dir / "run.json", summary)
    return summary


def _cmd_detect(args: argparse.Namespace) -> int:
    _require_tool("ffmpeg")
    _require_tool("SwitchAudioSource")
    inventory = _combine_audio_inventory()
    current_input = _current_audio_device("input")
    current_output = _current_audio_device("output")
    payload = {
        "current_input": current_input,
        "current_output": current_output,
        "audio_devices": [dataclasses.asdict(dev) for dev in inventory],
        "hid_devices": [dataclasses.asdict(dev) for dev in _list_hid_devices()],
    }
    if args.json:
        print(_json_dumps(payload))
        return 0

    print("audio devices:")
    for dev in inventory:
        role = []
        if dev.input_channels:
            role.append(f"in={dev.input_channels}")
        if dev.output_channels:
            role.append(f"out={dev.output_channels}")
        if dev.avfoundation_index is not None:
            role.append(f"avf={dev.avfoundation_index}")
        if dev.sample_rate:
            role.append(f"sr={dev.sample_rate}")
        if dev.name == current_input:
            role.append("current-input")
        if dev.name == current_output:
            role.append("current-output")
        print(f"  {dev.name}: " + ", ".join(role))
    if payload["hid_devices"]:
        print("hid devices:")
        for dev in payload["hid_devices"]:
            print(
                "  "
                f"{dev['product'] or '<no-product>'}: mode={dev['mode']} "
                f"mfg={dev['manufacturer'] or '<no-mfg>'} "
                f"serial={dev['serial'] or '<no-serial>'}"
            )
    return 0


def _cmd_probe_playback(args: argparse.Namespace) -> int:
    _require_tool("afplay")
    _require_tool("SwitchAudioSource")
    _play_audio(output_device=args.output_device, wav_path=args.wav)
    print(f"played: {args.wav}")
    print(f"output device: {_resolve_output_name(args.output_device)}")
    return 0


def _cmd_probe_capture(args: argparse.Namespace) -> int:
    _require_tool("ffmpeg")
    _capture_audio(
        input_device=args.input_device,
        duration_s=args.duration,
        sample_rate=args.sample_rate,
        channels=args.channels,
        out_path=args.out,
    )
    print(f"captured: {args.out}")
    print(f"input device: {_resolve_input_name(args.input_device)}")
    return 0


def _cmd_gen_sweep(args: argparse.Namespace) -> int:
    spec = SweepSpec(
        sample_rate=args.sample_rate,
        start_hz=args.start_hz,
        end_hz=args.end_hz,
        sweep_s=args.sweep_s,
        pre_s=args.pre_s,
        post_s=args.post_s,
        amplitude=args.amplitude,
        channels=args.channels,
        fade_s=args.fade_s,
    )
    manifest = _write_sweep(args.out, spec)
    manifest_path = args.json_out if args.json_out is not None else args.out.with_suffix(".json")
    _write_manifest(manifest_path, dataclasses.asdict(manifest))
    print(f"wrote sweep: {args.out}")
    print(f"wrote manifest: {manifest_path}")
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    manifest = _load_manifest(args.manifest) if args.manifest is not None else None
    compare_min_hz, compare_max_hz = _resolve_compare_band(
        manifest=manifest,
        compare_min_hz=args.compare_min_hz,
        compare_max_hz=args.compare_max_hz,
    )
    result = analyze_capture(
        stimulus_path=args.stimulus,
        capture_path=args.capture,
        out_dir=args.out_dir,
        channel_mode=args.channel,
        baseline_csv=args.baseline_csv,
        manifest_path=args.manifest,
        capture_lead_s=args.capture_lead_s,
        compare_min_hz=compare_min_hz,
        compare_max_hz=compare_max_hz,
        title=args.title or args.out_dir.name,
    )
    print(f"wrote metrics: {result.metrics_path}")
    print(f"classification: {result.metrics['classification']}")
    print(f"decision: {result.metrics['decision']}")
    print(f"snr_db: {result.metrics['snr_db']:.2f}")
    print(f"response csv: {result.response_mag_csv_path}")
    if result.response_mag_png_path is not None:
        print(f"response png: {result.response_mag_png_path}")
    return 0


def _cmd_run_once(args: argparse.Namespace) -> int:
    run_dir = args.run_dir if args.run_dir is not None else _run_dir(args.tag, DEFAULT_RUNS_ROOT)
    spec = SweepSpec(
        sample_rate=args.sample_rate,
        start_hz=args.start_hz,
        end_hz=args.end_hz,
        sweep_s=args.sweep_s,
        pre_s=args.pre_s,
        post_s=args.post_s,
        amplitude=args.amplitude,
        channels=args.stimulus_channels,
        fade_s=args.fade_s,
    )
    summary = _run_once(
        run_dir=run_dir,
        base_hex=args.hex,
        capture_a=args.capture_a,
        meta_a=args.meta_a,
        name_a=args.name_a,
        route=args.all_ch,
        input_device=args.input_device,
        output_device=args.output_device,
        stimulus_path=args.stimulus,
        stimulus_manifest=args.manifest,
        sweep_spec=spec,
        capture_sample_rate=args.capture_sample_rate,
        capture_channels=args.capture_channels,
        capture_lead_s=args.capture_lead_s,
        baseline_csv=args.baseline_csv,
        compare_min_hz=args.compare_min_hz,
        compare_max_hz=args.compare_max_hz,
        vid=args.vid,
        pid=args.pid,
        verbose=args.verbose,
    )
    print(_json_dumps(summary))
    return 0


def _cmd_run_matrix(args: argparse.Namespace) -> int:
    if not args.hex:
        raise SystemExit("run-matrix requires at least one --hex")
    root = args.root if args.root is not None else _run_dir(args.tag, DEFAULT_RUNS_ROOT)
    root.mkdir(parents=True, exist_ok=True)

    baseline_csv: Optional[Path] = None
    results: list[dict[str, object]] = []
    spec = SweepSpec(
        sample_rate=args.sample_rate,
        start_hz=args.start_hz,
        end_hz=args.end_hz,
        sweep_s=args.sweep_s,
        pre_s=args.pre_s,
        post_s=args.post_s,
        amplitude=args.amplitude,
        channels=args.stimulus_channels,
        fade_s=args.fade_s,
    )
    for idx, hex_path in enumerate(args.hex):
        tag = f"{idx:02d}_{hex_path.stem}"
        run_dir = root / tag
        summary = _run_once(
            run_dir=run_dir,
            base_hex=hex_path,
            capture_a=args.capture_a,
            meta_a=args.meta_a,
            name_a=args.name_a,
            route=args.all_ch,
            input_device=args.input_device,
            output_device=args.output_device,
            stimulus_path=args.stimulus,
            stimulus_manifest=args.manifest,
            sweep_spec=spec,
            capture_sample_rate=args.capture_sample_rate,
            capture_channels=args.capture_channels,
            capture_lead_s=args.capture_lead_s,
            baseline_csv=baseline_csv,
            compare_min_hz=args.compare_min_hz,
            compare_max_hz=args.compare_max_hz,
            vid=args.vid,
            pid=args.pid,
            verbose=args.verbose,
        )
        results.append(summary)
        if baseline_csv is None:
            baseline_csv = run_dir / "response_mag.csv"

    payload = {
        "root": str(root),
        "results": results,
    }
    _write_manifest(root / "summary.json", payload)
    print(_json_dumps(payload))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_detect = sub.add_parser("detect", help="enumerate audio and DLCP HID devices")
    p_detect.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    p_detect.set_defaults(func=_cmd_detect)

    p_play = sub.add_parser("probe-playback", help="play a WAV through the selected output device")
    p_play.add_argument("--output-device", default=DEFAULT_OUTPUT_DEVICE)
    p_play.add_argument("--wav", type=Path, required=True)
    p_play.set_defaults(func=_cmd_probe_playback)

    p_cap = sub.add_parser("probe-capture", help="capture a short WAV from the selected input device")
    p_cap.add_argument("--input-device", default=DEFAULT_INPUT_DEVICE)
    p_cap.add_argument("--duration", type=float, default=1.0)
    p_cap.add_argument("--sample-rate", type=int, default=DEFAULT_SWEEP_SR)
    p_cap.add_argument("--channels", type=int, default=DEFAULT_CAPTURE_CHANNELS)
    p_cap.add_argument("--out", type=Path, required=True)
    p_cap.set_defaults(func=_cmd_probe_capture)

    p_sweep = sub.add_parser("gen-sweep", help="generate a logarithmic sweep WAV and sidecar JSON")
    p_sweep.add_argument("--out", type=Path, required=True)
    p_sweep.add_argument("--json-out", type=Path, default=None)
    p_sweep.add_argument("--sample-rate", type=int, default=DEFAULT_SWEEP_SR)
    p_sweep.add_argument("--start-hz", type=float, default=DEFAULT_SWEEP_START_HZ)
    p_sweep.add_argument("--end-hz", type=float, default=DEFAULT_SWEEP_END_HZ)
    p_sweep.add_argument("--sweep-s", type=float, default=DEFAULT_SWEEP_LEN_S)
    p_sweep.add_argument("--pre-s", type=float, default=DEFAULT_PRE_S)
    p_sweep.add_argument("--post-s", type=float, default=DEFAULT_POST_S)
    p_sweep.add_argument("--amplitude", type=float, default=DEFAULT_SWEEP_AMPLITUDE)
    p_sweep.add_argument("--channels", type=int, default=2)
    p_sweep.add_argument("--fade-s", type=float, default=0.01)
    p_sweep.set_defaults(func=_cmd_gen_sweep)

    p_an = sub.add_parser("analyze", help="analyze a stimulus/capture pair and write metrics")
    p_an.add_argument("--stimulus", type=Path, required=True)
    p_an.add_argument("--manifest", type=Path, default=None)
    p_an.add_argument("--capture", type=Path, required=True)
    p_an.add_argument("--out-dir", type=Path, required=True)
    p_an.add_argument("--baseline-csv", type=Path, default=None)
    p_an.add_argument("--channel", default=DEFAULT_ANALYZE_CHANNEL)
    p_an.add_argument("--capture-lead-s", type=float, default=DEFAULT_CAPTURE_LEAD_S)
    p_an.add_argument("--compare-min-hz", type=float, default=None)
    p_an.add_argument("--compare-max-hz", type=float, default=None)
    p_an.add_argument("--title", default="")
    p_an.set_defaults(func=_cmd_analyze)

    def add_measure_args(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--hex", type=Path, default=None, help="flash this firmware before measurement")
        parser.add_argument("--capture-a", type=Path, default=None, help="preset A table capture to bake before flash")
        parser.add_argument("--meta-a", type=Path, default=None, help="optional preset A metadata sidecar")
        parser.add_argument("--name-a", default=None, help="ASCII config name fallback for --capture-a")
        parser.add_argument("--all-ch", type=str.upper, choices=sorted(ALL_CH_ROUTE_VALUES), default=None)
        parser.add_argument("--input-device", default=DEFAULT_INPUT_DEVICE)
        parser.add_argument("--output-device", default=DEFAULT_OUTPUT_DEVICE)
        parser.add_argument("--stimulus", type=Path, default=None, help="existing WAV stimulus to use")
        parser.add_argument("--manifest", type=Path, default=None, help="JSON sidecar for --stimulus")
        parser.add_argument("--sample-rate", type=int, default=DEFAULT_SWEEP_SR)
        parser.add_argument("--start-hz", type=float, default=DEFAULT_SWEEP_START_HZ)
        parser.add_argument("--end-hz", type=float, default=DEFAULT_SWEEP_END_HZ)
        parser.add_argument("--sweep-s", type=float, default=DEFAULT_SWEEP_LEN_S)
        parser.add_argument("--pre-s", type=float, default=DEFAULT_PRE_S)
        parser.add_argument("--post-s", type=float, default=DEFAULT_POST_S)
        parser.add_argument("--amplitude", type=float, default=DEFAULT_SWEEP_AMPLITUDE)
        parser.add_argument("--fade-s", type=float, default=0.01)
        parser.add_argument("--stimulus-channels", type=int, default=2)
        parser.add_argument("--capture-sample-rate", type=int, default=DEFAULT_SWEEP_SR)
        parser.add_argument("--capture-channels", type=int, default=DEFAULT_CAPTURE_CHANNELS)
        parser.add_argument("--capture-lead-s", type=float, default=DEFAULT_CAPTURE_LEAD_S)
        parser.add_argument("--baseline-csv", type=Path, default=None)
        parser.add_argument("--compare-min-hz", type=float, default=None)
        parser.add_argument("--compare-max-hz", type=float, default=None)
        parser.add_argument("--vid", type=int, default=DEFAULT_VID)
        parser.add_argument("--pid", type=int, default=DEFAULT_PID)
        parser.add_argument("-v", "--verbose", action="store_true")

    p_once = sub.add_parser("run-once", help="optionally flash firmware, then play/capture/analyze one run")
    p_once.add_argument("--tag", default="run")
    p_once.add_argument("--run-dir", type=Path, default=None)
    add_measure_args(p_once)
    p_once.set_defaults(func=_cmd_run_once)

    p_matrix = sub.add_parser("run-matrix", help="run the same measurement workflow across multiple firmware images")
    p_matrix.add_argument("--tag", default="matrix")
    p_matrix.add_argument("--root", type=Path, default=None)
    p_matrix.add_argument("--hex", type=Path, action="append", default=[])
    p_matrix.add_argument("--capture-a", type=Path, required=True)
    p_matrix.add_argument("--meta-a", type=Path, default=None)
    p_matrix.add_argument("--name-a", default=None)
    p_matrix.add_argument("--all-ch", type=str.upper, choices=sorted(ALL_CH_ROUTE_VALUES), default=None)
    p_matrix.add_argument("--input-device", default=DEFAULT_INPUT_DEVICE)
    p_matrix.add_argument("--output-device", default=DEFAULT_OUTPUT_DEVICE)
    p_matrix.add_argument("--stimulus", type=Path, default=None)
    p_matrix.add_argument("--manifest", type=Path, default=None)
    p_matrix.add_argument("--sample-rate", type=int, default=DEFAULT_SWEEP_SR)
    p_matrix.add_argument("--start-hz", type=float, default=DEFAULT_SWEEP_START_HZ)
    p_matrix.add_argument("--end-hz", type=float, default=DEFAULT_SWEEP_END_HZ)
    p_matrix.add_argument("--sweep-s", type=float, default=DEFAULT_SWEEP_LEN_S)
    p_matrix.add_argument("--pre-s", type=float, default=DEFAULT_PRE_S)
    p_matrix.add_argument("--post-s", type=float, default=DEFAULT_POST_S)
    p_matrix.add_argument("--amplitude", type=float, default=DEFAULT_SWEEP_AMPLITUDE)
    p_matrix.add_argument("--fade-s", type=float, default=0.01)
    p_matrix.add_argument("--stimulus-channels", type=int, default=2)
    p_matrix.add_argument("--capture-sample-rate", type=int, default=DEFAULT_SWEEP_SR)
    p_matrix.add_argument("--capture-channels", type=int, default=DEFAULT_CAPTURE_CHANNELS)
    p_matrix.add_argument("--capture-lead-s", type=float, default=DEFAULT_CAPTURE_LEAD_S)
    p_matrix.add_argument("--compare-min-hz", type=float, default=None)
    p_matrix.add_argument("--compare-max-hz", type=float, default=None)
    p_matrix.add_argument("--vid", type=int, default=DEFAULT_VID)
    p_matrix.add_argument("--pid", type=int, default=DEFAULT_PID)
    p_matrix.add_argument("-v", "--verbose", action="store_true")
    p_matrix.set_defaults(func=_cmd_run_matrix)

    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
