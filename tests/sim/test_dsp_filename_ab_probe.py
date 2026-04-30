from __future__ import annotations

from dlcp_fw.flash import dsp_filename_ab_probe as probe


# All tests in this module are backend-agnostic (Python-level
# behavioral models, hex/source byte comparisons, flash-tool plumbing,
# scenario runners).  No gpsim runtime, no rust facade.  Mark the
# whole module dual_supported so DLCP_SIM_BACKEND={rust,dual} does
# not auto-skip them.
import pytest

pytestmark = pytest.mark.dual_supported


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


def test_dlcp_ep0_large_read_streams_via_repeated_e7() -> None:
    dev = probe.DlcpEp0.__new__(probe.DlcpEp0)
    calls: list[tuple[int, int, bool, int]] = []

    def fake_poke(addr: int, value: int, in_dir: bool, read_len: int = 0) -> bytes:
        calls.append((addr, value, in_dir, read_len))
        return bytes([len(calls)]) * read_len

    dev._poke = fake_poke  # type: ignore[method-assign]

    data = probe.DlcpEp0.read_exact(dev, 0x240)

    assert len(data) == 0x240
    assert data[:0xFF] == bytes([1]) * 0xFF
    assert data[0xFF : 0x1FE] == bytes([2]) * 0xFF
    assert data[0x1FE :] == bytes([3]) * 0x42
    assert calls == [
        (0xE7, 0xFF, True, 0xFF),
        (0xE7, 0xFF, True, 0xFF),
        (0xE7, 0x42, True, 0x42),
    ]


def test_dump_flash_forwards_explicit_path(monkeypatch, tmp_path) -> None:
    seen: dict[str, object] = {}

    class FakeEp0:
        def __init__(self, vid: int, pid: int, path: bytes | None = None) -> None:
            seen["path"] = path
            self.ptr = 0

        def set_pointer(self, addr16: int) -> None:
            self.ptr = addr16

        def read_exact(self, n: int) -> bytes:
            return bytes([0x33] * n)

    monkeypatch.setattr(probe, "DlcpEp0", FakeEp0)

    out_path = tmp_path / "dump.bin"
    data = probe.dump_flash(
        out_path=out_path,
        vid=0x04D8,
        pid=0xFF89,
        path=b"hid-main-b",
        start=0x0800,
        size=4,
        chunk=2,
    )

    assert data == b"\x33\x33\x33\x33"
    assert out_path.read_bytes() == data
    assert seen["path"] == b"hid-main-b"
