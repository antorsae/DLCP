#!/usr/bin/env python3
"""Operator wrapper for the canonical V3.5 FilterData XML release flash path."""

from __future__ import annotations

from dlcp_fw.flash import dlcp_release_flash_common as _common
from dlcp_fw.flash import dlcp_main_flash as main_flash  # noqa: F401 – re-export for tests
from dlcp_fw.paths import (
    V35_FILTERDATA_PRESET_A,
    V35_FILTERDATA_PRESET_A_NAME,
    V35_FILTERDATA_PRESET_A_SHA256,
    V35_FILTERDATA_PRESET_B,
    V35_FILTERDATA_PRESET_B_NAME,
    V35_FILTERDATA_PRESET_B_SHA256,
    V35_MAIN_HEX,
)

FILTERDATA_A = V35_FILTERDATA_PRESET_A
FILTERDATA_B = V35_FILTERDATA_PRESET_B
FILTERDATA_MODE = "hfd-pz"
FILTERDATA_A_NAME = V35_FILTERDATA_PRESET_A_NAME
FILTERDATA_B_NAME = V35_FILTERDATA_PRESET_B_NAME
FILTERDATA_A_SHA256 = V35_FILTERDATA_PRESET_A_SHA256
FILTERDATA_B_SHA256 = V35_FILTERDATA_PRESET_B_SHA256
DEFAULT_PRESET_NAMES = {
    "A": FILTERDATA_A_NAME,
    "B": FILTERDATA_B_NAME,
}


def build_forward_argv(args, parser):
    return _common.build_forward_argv(
        args, parser,
        release_hex=V35_MAIN_HEX,
        version_label="V3.5",
        filterdata_a=FILTERDATA_A,
        filterdata_b=FILTERDATA_B,
        filterdata_mode=FILTERDATA_MODE,
        filterdata_a_name=FILTERDATA_A_NAME,
        filterdata_b_name=FILTERDATA_B_NAME,
        filterdata_a_sha256=FILTERDATA_A_SHA256,
        filterdata_b_sha256=FILTERDATA_B_SHA256,
    )


def main(argv: list[str] | None = None) -> int:
    return _common.release_main(
        argv,
        release_hex=V35_MAIN_HEX,
        version_label="V3.5",
        filterdata_a=FILTERDATA_A,
        filterdata_b=FILTERDATA_B,
        filterdata_mode=FILTERDATA_MODE,
        filterdata_a_name=FILTERDATA_A_NAME,
        filterdata_b_name=FILTERDATA_B_NAME,
        filterdata_a_sha256=FILTERDATA_A_SHA256,
        filterdata_b_sha256=FILTERDATA_B_SHA256,
    )


if __name__ == "__main__":
    raise SystemExit(main())
