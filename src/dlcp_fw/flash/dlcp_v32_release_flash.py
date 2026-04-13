#!/usr/bin/env python3
"""Operator wrapper for the canonical V3.2 baked-preset release flash path."""

from __future__ import annotations

from dlcp_fw.flash import dlcp_release_flash_common as _common
from dlcp_fw.flash import dlcp_main_flash as main_flash  # noqa: F401 – re-export for tests
from dlcp_fw.paths import V32_MAIN_HEX

CAPTURE_A_BIN = _common.CAPTURE_A_BIN
CAPTURE_A_META = _common.CAPTURE_A_META
CAPTURE_B_BIN = _common.CAPTURE_B_BIN
CAPTURE_B_META = _common.CAPTURE_B_META


def build_forward_argv(args, parser):
    return _common.build_forward_argv(
        args, parser,
        release_hex=V32_MAIN_HEX,
        version_label="V3.2",
        capture_a_bin=CAPTURE_A_BIN,
        capture_a_meta=CAPTURE_A_META,
        capture_b_bin=CAPTURE_B_BIN,
        capture_b_meta=CAPTURE_B_META,
    )


def main(argv: list[str] | None = None) -> int:
    return _common.release_main(
        argv,
        release_hex=V32_MAIN_HEX,
        version_label="V3.2",
        capture_a_bin=CAPTURE_A_BIN,
        capture_a_meta=CAPTURE_A_META,
        capture_b_bin=CAPTURE_B_BIN,
        capture_b_meta=CAPTURE_B_META,
    )


if __name__ == "__main__":
    raise SystemExit(main())
