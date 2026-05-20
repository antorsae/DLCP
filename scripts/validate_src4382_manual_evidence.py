#!/usr/bin/env python3
"""Validate the manual SRC4382 Auto Detect hardware evidence artifact."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import NamedTuple


REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
DEFAULT_EVIDENCE_RELATIVE_PATH = "artifacts/probes/v171_v32_ledger_gate/bug_src4382_ad_01_manual_evidence.md"
DEFAULT_EVIDENCE_PATH = REPO_ROOT / DEFAULT_EVIDENCE_RELATIVE_PATH


class ReleaseIdentity(NamedTuple):
    version: str
    revision: int

    @property
    def rev_hex(self) -> str:
        return f"0x{self.revision:02X}"

    @property
    def display(self) -> str:
        return f"{self.version} / rev {self.rev_hex}"


def current_release_identities() -> dict[str, ReleaseIdentity]:
    """Read the current canonical V1.71/V3.2 release identities from HEX."""

    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))

    from dlcp_fw.flash.dlcp_control_flash import (  # noqa: PLC0415
        detect_static_hex_control_release_info,
        parse_intel_hex,
    )
    from dlcp_fw.flash.dlcp_main_flash import (  # noqa: PLC0415
        detect_static_hex_eeprom_version,
    )
    from dlcp_fw.paths import V171_CONTROL_HEX, V32_MAIN_HEX  # noqa: PLC0415

    control_mem = parse_intel_hex(str(V171_CONTROL_HEX))
    control_info = detect_static_hex_control_release_info(control_mem)
    if control_info is None or control_info.revision is None:
        raise RuntimeError(f"cannot read CONTROL release revision from {V171_CONTROL_HEX}")
    suffix = (
        chr(control_info.sub)
        if 0x20 <= control_info.sub <= 0x7E
        else f"[0x{control_info.sub:02X}]"
    )
    control = ReleaseIdentity(
        version=f"V{control_info.major}.{control_info.minor}{suffix}",
        revision=control_info.revision,
    )

    main_mem = parse_intel_hex(str(V32_MAIN_HEX))
    main_info = detect_static_hex_eeprom_version(main_mem)
    if main_info is None:
        raise RuntimeError(f"cannot read MAIN EEPROM release revision from {V32_MAIN_HEX}")
    main = ReleaseIdentity(
        version=f"V{main_info.major}.{main_info.minor}",
        revision=main_info.revision,
    )

    return {"CONTROL": control, "MAIN": main}


def current_release_hashes() -> dict[str, str]:
    """Return SHA256 digests for the current canonical release HEX files."""

    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))

    from dlcp_fw.paths import V171_CONTROL_HEX, V32_MAIN_HEX  # noqa: PLC0415

    return {
        "CONTROL": hashlib.sha256(V171_CONTROL_HEX.read_bytes()).hexdigest(),
        "MAIN": hashlib.sha256(V32_MAIN_HEX.read_bytes()).hexdigest(),
    }


def _section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    start = text.find(marker)
    if start < 0:
        return ""
    next_heading = text.find("\n## ", start + len(marker))
    if next_heading < 0:
        return text[start:]
    return text[start:next_heading]


def _field_value(section: str, label: str) -> str | None:
    escaped = re.escape(label)
    match = re.search(rf"(?im)^[ \t]*{escaped}[ \t]*(.*)$", section)
    if match is None:
        return None
    return match.group(1).strip()


def _is_placeholder(value: str) -> bool:
    return value.strip().lower() in {"", "-", "n/a", "na", "tbd", "todo"}


def _starts_with_token(value: str, token: str) -> bool:
    return bool(re.match(rf"(?i)^\s*{re.escape(token)}\b", value))


def _section_detail(section: str) -> str:
    lines = section.splitlines()
    return "\n".join(line.strip() for line in lines[1:]).strip()


def _concrete_section(section: str, heading: str, errors: list[str]) -> None:
    value = _section_detail(section)
    if _is_placeholder(value):
        errors.append(f"section needs concrete entry: {heading}")


def _has_date_like_value(value: str) -> bool:
    month_name = (
        r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
        r"nov(?:ember)?|dec(?:ember)?)"
    )
    return any(
        re.search(pattern, value, flags=re.IGNORECASE)
        for pattern in (
            r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b",
            rf"\b{month_name}\s+\d{{1,2}},?\s+20\d{{2}}\b",
            rf"\b\d{{1,2}}\s+{month_name}\s+20\d{{2}}\b",
        )
    )


def _has_time_like_value(value: str) -> bool:
    return bool(
        re.search(r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:am|pm)?\b", value, re.IGNORECASE)
    )


def _concrete_date_time_section(section: str, heading: str, errors: list[str]) -> None:
    value = _section_detail(section)
    if _is_placeholder(value):
        errors.append(f"section needs concrete entry: {heading}")
        return
    if not _has_date_like_value(value):
        errors.append(f"section needs date-like value: {heading} -> {value!r}")
    if not _has_time_like_value(value):
        errors.append(f"section needs time-like value: {heading} -> {value!r}")


def _concrete_field(section: str, label: str, errors: list[str]) -> None:
    value = _field_value(section, label)
    if value is None:
        errors.append(f"missing field: {label}")
        return
    if _is_placeholder(value):
        errors.append(f"field needs concrete value: {label} -> {value!r}")


def _yes(section: str, label: str, errors: list[str]) -> None:
    value = _field_value(section, label)
    if value is None:
        errors.append(f"missing field: {label}")
        return
    if not _starts_with_token(value, "yes"):
        errors.append(f"field must be yes: {label} -> {value!r}")


def _release_identity(
    section: str,
    label: str,
    identity: ReleaseIdentity,
    errors: list[str],
) -> None:
    value = _field_value(section, label)
    if value is None:
        errors.append(f"missing field: {label}")
        return
    if identity.version not in value or identity.rev_hex.lower() not in value.lower():
        errors.append(
            f"firmware field must include current {identity.display}: "
            f"{label} -> {value!r}"
        )


def _release_hash(section: str, label: str, expected_sha256: str, errors: list[str]) -> None:
    value = _field_value(section, label)
    if value is None:
        errors.append(f"missing field: {label}")
        return
    if expected_sha256.lower() not in value.lower():
        errors.append(
            f"firmware hash field must include current SHA256 {expected_sha256}: "
            f"{label} -> {value!r}"
        )


def _no(section: str, label: str, errors: list[str]) -> None:
    value = _field_value(section, label)
    if value is None:
        errors.append(f"missing field: {label}")
        return
    if not _starts_with_token(value, "no"):
        errors.append(f"field must be no: {label} -> {value!r}")


def _yes_or_no(section: str, label: str, errors: list[str]) -> None:
    value = _field_value(section, label)
    if value is None:
        errors.append(f"missing field: {label}")
        return
    if not (_starts_with_token(value, "yes") or _starts_with_token(value, "no")):
        errors.append(f"field must start with yes or no: {label} -> {value!r}")


def _duration_minutes(value: str) -> float | None:
    value = value.lower()
    clock = re.search(r"\b(\d+):(\d{2})\b", value)
    if clock is not None:
        return int(clock.group(1)) * 60 + int(clock.group(2))
    total = 0.0
    found = False
    for amount, unit in re.findall(
        r"(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours|min|mins|minute|minutes)\b",
        value,
    ):
        found = True
        number = float(amount)
        if unit.startswith("h"):
            total += number * 60
        else:
            total += number
    if found:
        return total
    return None


def _parse_ir_snapshot(value: str) -> tuple[int, int, int, int] | None:
    """Parse an operator I/R before-after note such as `I0/R0 -> I1/R1`."""

    match = re.search(
        r"(?i)\bI\s*=?\s*([0-9a-f]+)\s*/\s*R\s*=?\s*([0-9a-f]+)"
        r"\s*(?:->|=>|to)\s*"
        r"I\s*=?\s*([0-9a-f]+)\s*/\s*R\s*=?\s*([0-9a-f]+)\b",
        value,
    )
    if match is None:
        return None
    return tuple(int(part, 16) for part in match.groups())


def _ir_snapshot(section: str, label: str, errors: list[str]) -> bool:
    value = _field_value(section, label)
    if value is None:
        errors.append(f"missing field: {label}")
        return False
    if _is_placeholder(value):
        errors.append(f"field needs concrete value: {label} -> {value!r}")
        return False
    parsed = _parse_ir_snapshot(value)
    if parsed is None:
        errors.append(
            f"field needs I/R before-after value like I0/R0 -> I0/R0: "
            f"{label} -> {value!r}"
        )
        return False
    before_i, before_r, after_i, after_r = parsed
    return after_i > before_i or after_r > before_r


def _yes_with_min_duration(
    section: str, label: str, minimum_minutes: float, errors: list[str]
) -> None:
    value = _field_value(section, label)
    if value is None:
        errors.append(f"missing field: {label}")
        return
    if not _starts_with_token(value, "yes"):
        errors.append(f"field must be yes: {label} -> {value!r}")
        return
    minutes = _duration_minutes(value)
    if minutes is None:
        errors.append(f"field needs parseable duration: {label} -> {value!r}")
        return
    if minutes < minimum_minutes:
        errors.append(
            f"field duration too short: {label} -> {value!r} "
            f"({minutes:g} min < {minimum_minutes:g} min)"
        )


def validate_text(text: str) -> list[str]:
    errors: list[str] = []
    if "BUG-SRC4382-AD-01" not in text:
        errors.append("missing BUG-SRC4382-AD-01 marker")

    required_sections = (
        "Date/Time",
        "Firmware",
        "Test Setup",
        "Fixed-Input Playback",
        "Auto Detect Playback",
        "User Actions While Playing",
        "Soak",
        "Verdict",
    )
    sections = {name: _section(text, name) for name in required_sections}
    for name, body in sections.items():
        if not body:
            errors.append(f"missing section: {name}")

    firmware = sections["Firmware"]
    try:
        identities = current_release_identities()
        hashes = current_release_hashes()
    except Exception as exc:
        identities = {}
        hashes = {}
        errors.append(f"could not read canonical release identities/hashes: {exc}")
    if identities:
        _release_identity(firmware, "CONTROL:", identities["CONTROL"], errors)
        _release_identity(firmware, "MAIN PB1:", identities["MAIN"], errors)
        _release_identity(firmware, "MAIN PB2:", identities["MAIN"], errors)
    if hashes:
        _release_hash(firmware, "CONTROL SHA256:", hashes["CONTROL"], errors)
        _release_hash(firmware, "MAIN PB1 SHA256:", hashes["MAIN"], errors)
        _release_hash(firmware, "MAIN PB2 SHA256:", hashes["MAIN"], errors)
    for label in (
        "CONTROL flashed/running V1.71? yes/no:",
        "MAIN PB1 visible/running V3.2? yes/no:",
        "MAIN PB2 visible/running V3.2? yes/no:",
    ):
        _yes(firmware, label, errors)

    _concrete_date_time_section(sections["Date/Time"], "Date/Time", errors)
    for label in (
        "Source/input:",
        "Preset:",
        "Volume:",
        "Audio material or measurement used for low-band check:",
    ):
        _concrete_field(sections["Test Setup"], label, errors)

    _yes(
        sections["Fixed-Input Playback"],
        "Normal low-band output? yes/no:",
        errors,
    )
    _concrete_field(
        sections["Fixed-Input Playback"],
        "Fixed digital sources tested after Auto Detect (S/PDIF, USB Audio, AES, Optical as available):",
        errors,
    )
    _no(
        sections["Fixed-Input Playback"],
        "Any fixed digital source silent? yes/no:",
        errors,
    )

    auto_detect = sections["Auto Detect Playback"]
    _yes(auto_detect, "Selected same source? yes/no:", errors)
    _yes(auto_detect, "Normal low-band output? yes/no:", errors)

    actions = sections["User Actions While Playing"]
    for label in (
        "Volume responsive? yes/no:",
        "Mute/unmute responsive? yes/no:",
        "Preset A/B responsive and audio correct after switch? yes/no:",
        "Standby/wake responsive and both MAINs recover? yes/no:",
        "Explicit input selection responsive? yes/no:",
    ):
        _yes(actions, label, errors)

    soak = sections["Soak"]
    _yes_with_min_duration(
        soak,
        "Auto Detect no-source duration >= 30 min? yes/no, duration:",
        30,
        errors,
    )
    _yes_with_min_duration(
        soak,
        "Fixed-input playback duration >= 1 h? yes/no, duration:",
        60,
        errors,
    )
    _no(soak, "UI stalls observed? yes/no:", errors)
    _yes_or_no(
        soak,
        "Volume A/B badge pulsing or abnormal LCD refresh observed? yes/no/details:",
        errors,
    )
    _no(soak, "Unexplained I/R growth observed? yes/no:", errors)
    has_ir_growth = False
    for label in (
        "PB1 before/after diag I/R:",
        "PB2 before/after diag I/R:",
    ):
        has_ir_growth = _ir_snapshot(soak, label, errors) or has_ir_growth
    if has_ir_growth:
        label = "I/R growth explanation if any:"
        value = _field_value(soak, label)
        if value is None:
            errors.append(f"missing field: {label}")
        elif _is_placeholder(value) or value.strip().lower().startswith("none"):
            errors.append(f"field needs concrete growth explanation: {label} -> {value!r}")

    verdict = sections["Verdict"]
    value = _field_value(verdict, "Pass/fail:")
    if value is None:
        errors.append("missing field: Pass/fail:")
    elif not bool(re.match(r"(?i)^\s*pass(?:ed)?\b", value)):
        errors.append(f"verdict must be pass: {value!r}")

    return errors


def validate_path(path: Path) -> list[str]:
    if not path.exists():
        return [f"evidence file does not exist: {path}"]
    return validate_text(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the manual SRC4382 Auto Detect evidence artifact before "
            "closing BUG-SRC4382-AD-01."
        )
    )
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=DEFAULT_EVIDENCE_PATH,
        help=f"evidence markdown path (default: {DEFAULT_EVIDENCE_PATH})",
    )
    args = parser.parse_args(argv)

    errors = validate_path(args.path)
    if errors:
        print(f"FAIL {args.path}")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"PASS {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
