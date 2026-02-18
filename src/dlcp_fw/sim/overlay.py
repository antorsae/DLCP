"""Simulation-only HEX overlay engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Mapping, Sequence

from .hexio import assert_bytes, parse_intel_hex, patch_bytes, write_intel_hex


class OverlayError(RuntimeError):
    """Overlay operation failed."""


@dataclass(frozen=True)
class OverlayManifest:
    name: str
    byte_patches: Mapping[int, int]
    preconditions: Mapping[int, int] = field(default_factory=dict)
    postconditions: Mapping[int, int] = field(default_factory=dict)
    description: str = ""


@dataclass(frozen=True)
class OverlayResult:
    manifest_name: str
    output_hex: Path
    changed_bytes: int


def apply_overlay(base_hex: Path, output_hex: Path, manifest: OverlayManifest) -> OverlayResult:
    mem = parse_intel_hex(base_hex)
    if manifest.preconditions:
        try:
            assert_bytes(mem, manifest.preconditions, label=f"{manifest.name}:pre")
        except Exception as exc:  # pragma: no cover - rewrap clarity
            raise OverlayError(str(exc)) from exc

    changed = patch_bytes(mem, manifest.byte_patches)

    if manifest.postconditions:
        try:
            assert_bytes(mem, manifest.postconditions, label=f"{manifest.name}:post")
        except Exception as exc:  # pragma: no cover - rewrap clarity
            raise OverlayError(str(exc)) from exc

    output_hex.parent.mkdir(parents=True, exist_ok=True)
    write_intel_hex(output_hex, mem)
    return OverlayResult(manifest_name=manifest.name, output_hex=output_hex, changed_bytes=changed)


def apply_overlays(base_hex: Path, output_hex: Path, manifests: Sequence[OverlayManifest]) -> list[OverlayResult]:
    if not manifests:
        output_hex.parent.mkdir(parents=True, exist_ok=True)
        output_hex.write_bytes(base_hex.read_bytes())
        return []

    current = base_hex
    temp_results: list[OverlayResult] = []
    for i, manifest in enumerate(manifests, 1):
        dst = output_hex if i == len(manifests) else output_hex.with_suffix(f".stage{i}.hex")
        result = apply_overlay(current, dst, manifest)
        temp_results.append(result)
        current = dst

    # Remove intermediate stages to keep artifacts deterministic.
    for res in temp_results[:-1]:
        try:
            res.output_hex.unlink()
        except FileNotFoundError:
            pass

    return temp_results


def summary(results: Iterable[OverlayResult]) -> Dict[str, int]:
    return {r.manifest_name: r.changed_bytes for r in results}
