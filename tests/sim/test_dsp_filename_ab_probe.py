from __future__ import annotations

from dlcp_fw.flash import dsp_filename_ab_probe as probe


def _mk_blob(size: int, fill: int = 0xFF) -> bytearray:
    return bytearray([fill] * size)


def test_analyze_bytes_no_changes() -> None:
    start = 0x0800
    size = 0x7800
    before = bytes(_mk_blob(size))
    after = bytes(before)

    out = probe.analyze_bytes(before, after, start_addr=start)
    assert out.total_changed == 0
    assert out.changed_ranges == []
    assert out.inference == "No byte changes detected."


def test_analyze_bytes_tail_only_change() -> None:
    start = 0x0800
    size = 0x7800
    before = _mk_blob(size)
    after = bytearray(before)

    # Tail area inside 0x5F00..0x5FFF only.
    for addr, val in [(0x5F30, 0x12), (0x5FA8, 0x34)]:
        after[addr - start] = val

    out = probe.analyze_bytes(bytes(before), bytes(after), start_addr=start)
    assert out.total_changed == 2
    assert out.region_counts["dsp_table_tail_5f00_5fff"] == 2
    assert out.region_counts["dsp_table_main_5600_5eff"] == 0
    assert "Tail-only table changes" in out.inference


def test_analyze_bytes_table_main_change() -> None:
    start = 0x0800
    size = 0x7800
    before = _mk_blob(size)
    after = bytearray(before)

    # Main table payload-ish area.
    after[0x561C - start] = 0x11
    after[0x561D - start] = 0x22

    out = probe.analyze_bytes(bytes(before), bytes(after), start_addr=start)
    assert out.total_changed == 2
    assert out.region_counts["dsp_table_main_5600_5eff"] == 2
    assert out.region_counts["dsp_table_tail_5f00_5fff"] == 0
    assert "dsp_table_main" in out.inference.lower() or "coefficient" in out.inference.lower()
