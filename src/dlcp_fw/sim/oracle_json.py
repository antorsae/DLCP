"""Small JSON extraction helper for model-oracle command output."""

from __future__ import annotations

import json
from typing import Any


def extract_json_object(text: str) -> dict[str, Any]:
    """Return the last balanced top-level JSON object in ``text``.

    Model commands often wrap JSON in prose or fenced blocks.  The scanner is
    string-aware, so braces inside JSON strings do not corrupt the match.
    """
    text = text.strip()
    if "```" in text:
        for chunk in text.split("```"):
            candidate = chunk.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            if candidate.startswith("{"):
                try:
                    value = json.loads(candidate)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    return value

    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = None
    if isinstance(value, dict):
        return value

    depth = 0
    start = -1
    candidate = None
    in_string = False
    escape = False
    for index, char in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            if depth:
                depth -= 1
                if depth == 0 and start >= 0:
                    candidate = text[start : index + 1]

    if candidate is None:
        raise ValueError("no JSON object found in model output")
    value = json.loads(candidate)
    if not isinstance(value, dict):
        raise ValueError("model output JSON is not an object")
    return value
