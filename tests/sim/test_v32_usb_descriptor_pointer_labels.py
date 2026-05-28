"""V3.2 USB descriptor pointer relocation guards."""

from __future__ import annotations

import shutil

import pytest

from dlcp_fw.paths import V32_MAIN_ASM, V32_MAIN_HEX
from dlcp_fw.sim.hexio import parse_intel_hex
from dlcp_fw.sim.v30_symbols import assemble_v30


pytestmark = pytest.mark.dual_supported


def test_v32_usb_descriptor_seeds_use_labels_not_raw_addresses() -> None:
    text = V32_MAIN_ASM.read_text(encoding="utf-8")

    for label in (
        "usb_config_descriptor",
        "usb_hid_descriptor",
        "usb_hid_report_descriptor",
        "usb_device_descriptor",
    ):
        assert f"HIGH({label})" in text
        assert f"LOW({label})" in text

    old_raw_sequences = (
        ("0x10", "0x2C"),
        ("0x10", "0x3E"),
        ("0x10", "0x55"),
        ("0x10", "0x88"),
    )
    for high, low in old_raw_sequences:
        assert (
            f"movlw       {high}\n"
            "    movwf       ram_0x076, BANKED\n"
            f"    movlw       {low}\n"
            "    movwf       ram_0x075, BANKED"
        ) not in text


def test_v32_usb_descriptor_label_refactor_is_hex_identical(tmp_path) -> None:
    asm_path = tmp_path / V32_MAIN_ASM.name
    hex_path = tmp_path / V32_MAIN_HEX.name
    lst_path = tmp_path / V32_MAIN_HEX.with_suffix(".lst").name
    shutil.copy2(V32_MAIN_ASM, asm_path)
    shutil.copy2(V32_MAIN_ASM.parent / "dlcp_main_ram.inc", tmp_path / "dlcp_main_ram.inc")

    assemble_v30(asm_path, hex_path, output_lst=lst_path)

    assert parse_intel_hex(hex_path) == parse_intel_hex(V32_MAIN_HEX)
