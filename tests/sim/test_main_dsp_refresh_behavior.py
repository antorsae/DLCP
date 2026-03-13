"""Characterization tests for MAIN DSP refresh behavior (boot/preset/upload paths)."""

from __future__ import annotations

from pathlib import Path

from dlcp_fw.paths import PATCHED_MAIN_HEX
from dlcp_fw.sim.hexio import parse_intel_hex
from dlcp_fw.sim.main_model import MainUnitModel
from dlcp_fw.sim.protocol import SerialFrame
from dlcp_fw.sim.scenarios import build_payload


ROOT = Path(__file__).resolve().parent.parent.parent
MAIN_DISASM = ROOT / "firmware" / "disasm" / "main" / "gpdasm_output.asm"


def _function_block(text: str, start_label: str, end_label: str) -> str:
    start = text.find(start_label)
    if start < 0:
        raise AssertionError(f"missing disasm label: {start_label}")
    end = text.find(end_label, start + len(start_label))
    if end < 0:
        raise AssertionError(f"missing disasm label: {end_label}")
    return text[start:end]


def test_boot_path_contains_table_apply_call() -> None:
    """Boot/init path still issues a table->DSP apply call (function_084)."""
    text = MAIN_DISASM.read_text(encoding="utf-8", errors="replace")
    assert "002e28:  ecba  call    function_084, 0x0                    ; dest: 0x004574" in text


def test_usb_upload_path_does_not_call_table_apply_directly() -> None:
    """
    USB coefficient upload path writes flash but does not directly call table apply.

    This is a behavior characterization of v2.4 code path around function_021.
    """
    text = MAIN_DISASM.read_text(encoding="utf-8", errors="replace")
    upload_block = _function_block(text, "function_021:", "function_022:")
    assert "dest: 0x004028" in upload_block  # table read helper
    assert "dest: 0x003dac" in upload_block  # erase helper
    assert "dest: 0x002e6e" in upload_block  # write helper
    assert "dest: 0x004574" not in upload_block  # no direct apply call in upload block


def test_cmd20_refreshes_on_change_only_with_correct_bank_digest(patched_main_hex: Path) -> None:
    """
    Preset command refreshes DSP on actual A/B transitions only (idempotent steady state).
    """
    m = MainUnitModel.from_hex("main", 1, patched_main_hex)

    payload_a = build_payload(0x11)
    payload_b = build_payload(0x7C)
    m.upload_hfd_table(payload_a)  # preset A by default
    digest_a = m.table_digest(0x5600)

    assert m.process_frame(SerialFrame(route=0xB0, cmd=0x20, data=0x01)) is True
    assert m.apply_count == 1
    assert m.dsp_ingest[-1].table_base == 0x4A00

    m.upload_hfd_table(payload_b)  # now writes preset B bank
    digest_b = m.table_digest(0x4A00)

    # Duplicate "set B" must not trigger extra apply.
    assert m.process_frame(SerialFrame(route=0xB0, cmd=0x20, data=0x01)) is True
    assert m.apply_count == 1
    assert m.dsp_ingest[-1].table_base == 0x4A00
    assert m.dsp_ingest[-1].table_sha256 != digest_b

    # Changing preset does trigger apply and uses active bank content.
    assert m.process_frame(SerialFrame(route=0xB0, cmd=0x20, data=0x00)) is True
    assert m.apply_count == 2
    assert m.dsp_ingest[-1].table_base == 0x5600
    assert m.dsp_ingest[-1].table_sha256 == digest_a

    assert m.process_frame(SerialFrame(route=0xB0, cmd=0x20, data=0x01)) is True
    assert m.apply_count == 3
    assert m.dsp_ingest[-1].table_base == 0x4A00
    assert m.dsp_ingest[-1].table_sha256 == digest_b


def test_usb_upload_in_active_preset_updates_flash_without_auto_apply(patched_main_hex: Path) -> None:
    """
    Characterize reported bug: upload-in-place modifies B bank but does not auto-refresh DSP.
    """
    m = MainUnitModel.from_hex("main", 1, patched_main_hex)

    # Move to preset B once (this applies current B table once).
    m.set_preset(1)
    assert m.apply_count == 1
    initial_ingest_sha = m.dsp_ingest[-1].table_sha256

    payload_b_v1 = build_payload(0x33)
    m.upload_hfd_table(payload_b_v1)
    digest_v1 = m.table_digest(0x4A00)
    assert digest_v1 != initial_ingest_sha
    assert m.apply_count == 1
    assert m.dsp_ingest[-1].table_sha256 == initial_ingest_sha

    payload_b_v2 = build_payload(0x34)
    m.upload_hfd_table(payload_b_v2)
    digest_v2 = m.table_digest(0x4A00)
    assert digest_v2 != digest_v1
    assert m.apply_count == 1
    assert m.dsp_ingest[-1].table_sha256 == initial_ingest_sha

    # Manual A->B toggle forces refresh and ingests latest B upload.
    m.set_preset(0)
    m.set_preset(1)
    assert m.apply_count == 3
    assert m.dsp_ingest[-1].table_base == 0x4A00
    assert m.dsp_ingest[-1].table_sha256 == digest_v2


def test_cmd20_stub_contains_apply_calls_in_built_hex() -> None:
    """Patched cmd=0x20 stub still contains the two call-apply opcodes."""
    mem = parse_intel_hex(PATCHED_MAIN_HEX)
    # call 0x4574 encoding appears twice in cmd_tail_patch (preset A / preset B branches).
    want = [0xBA, 0xEC, 0x22, 0xF0]
    hits = [
        a
        for a in range(0x54C0, 0x5510)
        if all(mem.get(a + i, 0xFF) == want[i] for i in range(4))
    ]
    assert len(hits) >= 2
