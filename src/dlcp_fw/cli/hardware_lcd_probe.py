#!/usr/bin/env python3
"""Real-hardware LCD probe using a tuned UVC camera and Vision OCR."""

from __future__ import annotations

import argparse
import collections
import dataclasses
import json
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import time
from typing import Any

from dlcp_fw.paths import ARTIFACTS_DIR


DEFAULT_CAMERA_NAME = "HD Pro Webcam C920"
DEFAULT_CAMERA_VENDOR = 1133
DEFAULT_CAMERA_PRODUCT = 2194
DEFAULT_CAMERA_ADDRESS = 1
DEFAULT_CAMERA_ZOOM = 500
DEFAULT_CAMERA_FOCUS = 140
DEFAULT_CAMERA_EXPOSURE = 156
DEFAULT_CAMERA_GAIN = 80
DEFAULT_CAMERA_SHARPNESS = 200
DEFAULT_CAPTURE_COUNT = 5
DEFAULT_WARMUP_S = 1.1
DEFAULT_OUTPUT_ROOT = ARTIFACTS_DIR / "probes" / "hardware_lcd"


_CAPTURE_SWIFT = r"""
import Foundation
import AVFoundation
import AppKit
import CoreImage

final class Grabber: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    let session = AVCaptureSession()
    let queue = DispatchQueue(label: "grabber.queue")
    let semaphore = DispatchSemaphore(value: 0)
    var frames: [NSImage] = []
    var started = Date()
    let captureAfter: Double
    let maxFrames: Int
    let device: AVCaptureDevice

    init(device: AVCaptureDevice, captureAfter: Double, maxFrames: Int) {
        self.device = device
        self.captureAfter = captureAfter
        self.maxFrames = maxFrames
        super.init()
    }

    func setup() throws {
        session.beginConfiguration()
        if session.canSetSessionPreset(.hd1920x1080) {
            session.sessionPreset = .hd1920x1080
        } else if session.canSetSessionPreset(.hd1280x720) {
            session.sessionPreset = .hd1280x720
        } else if session.canSetSessionPreset(.high) {
            session.sessionPreset = .high
        }

        let input = try AVCaptureDeviceInput(device: device)
        if session.canAddInput(input) {
            session.addInput(input)
        }

        let output = AVCaptureVideoDataOutput()
        output.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA]
        output.alwaysDiscardsLateVideoFrames = true
        output.setSampleBufferDelegate(self, queue: queue)
        if session.canAddOutput(output) {
            session.addOutput(output)
        }
        session.commitConfiguration()
    }

    func capture() {
        started = Date()
        session.startRunning()
        _ = semaphore.wait(timeout: .now() + 8)
        session.stopRunning()
    }

    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        let elapsed = Date().timeIntervalSince(started)
        guard elapsed >= captureAfter else { return }
        guard let pb = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        let ci = CIImage(cvPixelBuffer: pb)
        let ctx = CIContext()
        guard let cg = ctx.createCGImage(ci, from: ci.extent) else { return }
        let img = NSImage(cgImage: cg, size: NSSize(width: cg.width, height: cg.height))
        frames.append(img)
        if frames.count >= maxFrames {
            semaphore.signal()
        }
    }
}

func save(_ image: NSImage, to path: String) throws {
    var rect = CGRect(origin: .zero, size: image.size)
    guard let cg = image.cgImage(forProposedRect: &rect, context: nil, hints: nil) else {
        throw NSError(domain: "cg", code: 1)
    }
    let rep = NSBitmapImageRep(cgImage: cg)
    guard let data = rep.representation(using: .jpeg, properties: [.compressionFactor: 0.95]) else {
        throw NSError(domain: "jpeg", code: 2)
    }
    try data.write(to: URL(fileURLWithPath: path))
}

let selector = CommandLine.arguments[1]
let outPath = CommandLine.arguments[2]
let warmup = Double(CommandLine.arguments[3])!
let types: [AVCaptureDevice.DeviceType] = [.external, .builtInWideAngleCamera, .deskViewCamera]
let devices = AVCaptureDevice.DiscoverySession(deviceTypes: types, mediaType: .video, position: .unspecified).devices

guard let dev = devices.first(where: { $0.uniqueID == selector || $0.localizedName == selector }) else {
    fputs("device not found\n", stderr)
    exit(1)
}

let g = Grabber(device: dev, captureAfter: warmup, maxFrames: 1)
try g.setup()
g.capture()
guard let img = g.frames.last else {
    fputs("no frame\n", stderr)
    exit(2)
}
try save(img, to: outPath)
print(outPath)
"""


_OCR_SWIFT = r"""
import Foundation
import Vision
import AppKit

struct Observation: Encodable {
    let text: String
    let confidence: Float
    let x: Double
    let y: Double
    let w: Double
    let h: Double
}

let path = CommandLine.arguments[1]
let url = URL(fileURLWithPath: path)
guard let image = NSImage(contentsOf: url) else {
    fputs("failed to load image\n", stderr)
    exit(1)
}
var rect = CGRect(origin: .zero, size: image.size)
guard let cgImage = image.cgImage(forProposedRect: &rect, context: nil, hints: nil) else {
    fputs("failed to get cgImage\n", stderr)
    exit(1)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = false
request.recognitionLanguages = ["en-US"]

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
try handler.perform([request])

let observations = (request.results ?? []).compactMap { item -> Observation? in
    guard let top = item.topCandidates(1).first else { return nil }
    let box = item.boundingBox
    return Observation(
        text: top.string,
        confidence: top.confidence,
        x: Double(box.origin.x),
        y: Double(box.origin.y),
        w: Double(box.size.width),
        h: Double(box.size.height)
    )
}

let data = try JSONEncoder().encode(observations)
FileHandle.standardOutput.write(data)
"""


@dataclasses.dataclass(frozen=True)
class OcrObservation:
    text: str
    confidence: float
    x: float
    y: float
    w: float
    h: float


@dataclasses.dataclass(frozen=True)
class CaptureResult:
    image_path: Path
    observations: list[OcrObservation]
    line1: str | None
    line2: str | None


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, text=True, capture_output=True)


def _norm(text: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", text.upper())


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            replace = prev[j - 1] + (ca != cb)
            cur.append(min(ins, delete, replace))
        prev = cur
    return prev[-1]


def _looks_like(text: str, target: str, *, max_dist: int = 2) -> bool:
    norm = _norm(text)
    goal = _norm(target)
    if not norm:
        return False
    # Forward substring: target appears inside the observation
    # (e.g. "WAITING FOR DLCP V32" matches "WAITING FOR DLCP").
    if goal in norm:
        return True
    # Reverse substring: the observation appears inside the target.
    # Only allow when norm is a meaningful fragment (>= 3 chars), not
    # a single OCR character that happens to land inside a template
    # string (codex review of #43: a stray "P" was matching both
    # "PRESET" and "WAITINGFORDLCP" on PB Diag-page captures).
    if norm in goal and len(norm) >= 3:
        return True
    return _levenshtein(norm, goal) <= max_dist


def _group_rows(observations: list[OcrObservation]) -> tuple[str, str]:
    """Group OCR observations into (top_row_text, bottom_row_text)
    by clustering on y-coordinate.  Within each row, observations are
    ordered by x-coordinate and joined with spaces.

    The HD44780 LCD has two rows; in the camera frame they appear at
    distinct y-bands separated by a noticeable gap.  We split at the
    largest adjacent y-gap.  When all observations cluster together
    (gap < 0.05 in normalised image coords), they are treated as a
    single row and bottom_row_text is empty.

    Codex review of #43.
    """
    if not observations:
        return "", ""
    # Sort by y descending: top of the camera frame comes first.  In
    # the Vision framework's normalised coordinate space, y=1 is the
    # top edge.
    sorted_obs = sorted(observations, key=lambda item: -item.y)
    if len(sorted_obs) == 1:
        return sorted_obs[0].text.strip(), ""
    largest_gap = 0.0
    split_idx = 0
    for i in range(len(sorted_obs) - 1):
        gap = sorted_obs[i].y - sorted_obs[i + 1].y
        if gap > largest_gap:
            largest_gap = gap
            split_idx = i
    if largest_gap < 0.05:
        ordered = sorted(sorted_obs, key=lambda item: item.x)
        return (
            " ".join(o.text.strip() for o in ordered if o.text.strip()),
            "",
        )
    top = sorted(sorted_obs[: split_idx + 1], key=lambda item: item.x)
    bottom = sorted(sorted_obs[split_idx + 1 :], key=lambda item: item.x)
    top_text = " ".join(o.text.strip() for o in top if o.text.strip())
    bottom_text = " ".join(o.text.strip() for o in bottom if o.text.strip())
    return top_text, bottom_text


def _extract_pb_diag(
    observations: list[OcrObservation],
) -> tuple[str | None, str | None]:
    """First-pass extractor for the V1.71 Tier-1 PB Diagnostics page.

    Per docs/V32_DIAG_TIER1_SPEC.md (and V1.71 CONTROL asm:3603+
    which writes 'P','B','1' at row 0 cols 0..2 on state 4 / PB1
    Diag, and 'P','B','2' on state 5 / PB2 Diag), the LCD shows
    "PBn" (optionally with ":" + counter cells) on row 0 and one of
    "OK" / "n/a" / sparse counter cells on row 1.

    Returns (line1, line2) when row 0 normalises to "PB1*" or "PB2*"
    -- raw concatenated row text, no firmware-string snapping --
    or (None, None) otherwise so the legacy snapper can run.

    Codex review of #43: without this short-circuit, single-character
    OCR fragments from Diag-page cells (e.g. "P", "I", "D") were
    being snapped to "WAITING FOR DLCP" / "Preset" / "Active: B" by
    the legacy `_pick_lines` template matcher.
    """
    top_text, bottom_text = _group_rows(observations)
    norm_top = _norm(top_text)
    if not (norm_top.startswith("PB1") or norm_top.startswith("PB2")):
        return None, None
    return top_text, bottom_text


def _pick_lines(observations: list[OcrObservation]) -> tuple[str | None, str | None]:
    # First-pass: detect PB Diag page (Tier-1 layout) and return
    # raw row strings before legacy firmware-string snapping kicks
    # in.  Codex review of #43 -- the snapper was hallucinating
    # "WAITING FOR DLCP" / "Preset" / "Active: B" when fed
    # fragmented Diag-page OCR.
    pb_line1, pb_line2 = _extract_pb_diag(observations)
    if pb_line1 is not None:
        return pb_line1, pb_line2

    ordered = sorted(observations, key=lambda item: (-item.y, item.x))
    line1: str | None = None
    line2: str | None = None
    active_letter: str | None = None
    active_seen = False

    for obs in ordered:
        text = obs.text.strip()
        if not text:
            continue
        norm = _norm(text)
        if norm in {"A", "B"}:
            # Standalone single-letter observation: stage as a
            # candidate active-letter, but require Volume or Active
            # context elsewhere in the frame before emitting.  See
            # codex review of #43 -- a stray "B" from a Diag-page
            # cell was being emitted as "Active: B" without context.
            active_letter = norm
            continue
        if "DLCP" in norm or _looks_like(text, "WAITING FOR DLCP", max_dist=5):
            line1 = "WAITING FOR DLCP"
            continue
        if "ZZZ" in norm:
            line1 = "Zzz..."
            continue
        if _looks_like(text, "Preset"):
            line1 = "Preset"
            continue
        if _looks_like(text, "Volume"):
            line1 = "Volume"
            preset_match = re.search(r"\b([AB])\b\s*$", text, flags=re.IGNORECASE)
            if preset_match is not None:
                active_letter = preset_match.group(1).upper()
            continue
        if _looks_like(text, "Active", max_dist=3):
            active_seen = True
            suffix = ""
            if norm.endswith("A"):
                suffix = " A"
                active_letter = "A"
            elif norm.endswith("B"):
                suffix = " B"
                active_letter = "B"
            line2 = f"Active:{suffix}".rstrip()

    # Emit `Active: A/B` only when the frame also showed a Volume
    # screen (which carries the active letter alongside the level)
    # or an explicit Active line.  Without that context, a
    # standalone "A"/"B" observation is more likely a Diag-page
    # cell fragment than an active-preset indicator.  Codex review
    # of #43.
    if active_letter is not None and (line1 == "Volume" or active_seen):
        line2 = f"Active: {active_letter}"
    elif active_seen:
        line2 = "Active:"

    return line1, line2


def _configure_camera(args: argparse.Namespace) -> dict[str, object]:
    resolved_address = _resolve_uvcc_address(
        vendor=args.vendor,
        product=args.product,
        preferred_address=args.address,
        selector=args.camera_selector,
    )
    base = [
        "npx",
        "uvcc",
        "--vendor",
        str(args.vendor),
        "--product",
        str(args.product),
        "--address",
        str(resolved_address),
    ]
    for control, value in [
        ("absolute_zoom", args.zoom),
        ("auto_focus", 0),
        ("absolute_focus", args.focus),
        ("auto_exposure_mode", 1),
        ("auto_exposure_priority", 0),
        ("absolute_exposure_time", args.exposure),
        ("gain", args.gain),
        ("sharpness", args.sharpness),
    ]:
        _run(base + ["set", control, str(value)])
    config = json.loads(_run(base + ["export"]).stdout)
    config["_resolved_address"] = resolved_address
    return config


def _list_uvcc_devices() -> list[dict[str, Any]]:
    payload = json.loads(_run(["npx", "uvcc", "devices"]).stdout)
    if not isinstance(payload, list):
        raise RuntimeError("uvcc devices did not return a JSON list")
    return payload


def _resolve_uvcc_address(
    *,
    vendor: int,
    product: int,
    preferred_address: int,
    selector: str,
) -> int:
    devices = [
        item
        for item in _list_uvcc_devices()
        if int(item.get("vendor", -1)) == vendor and int(item.get("product", -1)) == product
    ]
    if not devices:
        return preferred_address
    if any(int(item.get("address", -1)) == preferred_address for item in devices):
        return preferred_address
    selector_matches = [item for item in devices if str(item.get("name", "")) == selector]
    if len(selector_matches) == 1:
        return int(selector_matches[0]["address"])
    if len(devices) == 1:
        return int(devices[0]["address"])
    raise RuntimeError(
        "multiple matching UVC devices found but the requested address did not match; "
        "pass --address explicitly"
    )


def _capture_frame(capture_swift: Path, selector: str, out_path: Path, warmup_s: float) -> None:
    _run(["swift", str(capture_swift), selector, str(out_path), f"{warmup_s:.3f}"])


def _ocr_frame(ocr_swift: Path, image_path: Path) -> list[OcrObservation]:
    payload = json.loads(_run(["swift", str(ocr_swift), str(image_path)]).stdout)
    return [OcrObservation(**item) for item in payload]


def _consensus(values: list[str | None]) -> str | None:
    filtered = [value for value in values if value]
    if not filtered:
        return None
    return collections.Counter(filtered).most_common(1)[0][0]


def _consensus_active(values: list[str | None]) -> str | None:
    filtered = [value for value in values if value]
    if not filtered:
        return None
    letters = []
    saw_prefix = False
    for value in filtered:
        norm = _norm(value)
        if norm.startswith("ACTIVE"):
            saw_prefix = True
            if norm.endswith("A"):
                letters.append("A")
            elif norm.endswith("B"):
                letters.append("B")
    if not saw_prefix:
        return _consensus(filtered)
    if letters and len(set(letters)) == 1:
        return f"Active: {letters[0]}"
    if letters:
        return collections.Counter(f"Active: {letter}" for letter in letters).most_common(1)[0][0]
    return "Active:"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera-selector", default=DEFAULT_CAMERA_NAME)
    parser.add_argument("--vendor", type=int, default=DEFAULT_CAMERA_VENDOR)
    parser.add_argument("--product", type=int, default=DEFAULT_CAMERA_PRODUCT)
    parser.add_argument("--address", type=int, default=DEFAULT_CAMERA_ADDRESS)
    parser.add_argument("--zoom", type=int, default=DEFAULT_CAMERA_ZOOM)
    parser.add_argument("--focus", type=int, default=DEFAULT_CAMERA_FOCUS)
    parser.add_argument("--exposure", type=int, default=DEFAULT_CAMERA_EXPOSURE)
    parser.add_argument("--gain", type=int, default=DEFAULT_CAMERA_GAIN)
    parser.add_argument("--sharpness", type=int, default=DEFAULT_CAMERA_SHARPNESS)
    parser.add_argument("--captures", type=int, default=DEFAULT_CAPTURE_COUNT)
    parser.add_argument("--warmup-s", type=float, default=DEFAULT_WARMUP_S)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--skip-configure", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    run_root = args.output_root / "runs" / time.strftime("%Y%m%d_%H%M%S")
    run_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="dlcp_lcd_probe_") as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        capture_swift = tmpdir / "capture.swift"
        ocr_swift = tmpdir / "ocr.swift"
        capture_swift.write_text(textwrap.dedent(_CAPTURE_SWIFT))
        ocr_swift.write_text(textwrap.dedent(_OCR_SWIFT))

        config = None
        if not args.skip_configure:
            config = _configure_camera(args)
            resolved = config.get("_resolved_address")
            if isinstance(resolved, int):
                args.address = resolved

        captures: list[CaptureResult] = []
        for index in range(args.captures):
            image_path = run_root / f"capture_{index + 1}.jpg"
            _capture_frame(capture_swift, args.camera_selector, image_path, args.warmup_s)
            observations = _ocr_frame(ocr_swift, image_path)
            line1, line2 = _pick_lines(observations)
            captures.append(CaptureResult(image_path=image_path, observations=observations, line1=line1, line2=line2))

    summary = {
        "camera_selector": args.camera_selector,
        "uvcc_target": {"vendor": args.vendor, "product": args.product, "address": args.address},
        "configured": config,
        "captures": [
            {
                "image_path": str(item.image_path),
                "line1": item.line1,
                "line2": item.line2,
                "observations": [dataclasses.asdict(obs) for obs in item.observations],
            }
            for item in captures
        ],
        "consensus": {
            "line1": _consensus([item.line1 for item in captures]),
            "line2": _consensus_active([item.line2 for item in captures]),
        },
    }
    summary_path = run_root / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True))

    print(f"run_root: {run_root}")
    print(f"summary:  {summary_path}")
    print(f"line1:    {summary['consensus']['line1']}")
    print(f"line2:    {summary['consensus']['line2']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
