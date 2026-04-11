from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from dlcp_fw.sim import chain_gpsim as cg
from dlcp_fw.sim import main_gpsim as mg
from dlcp_fw.sim import main_gpsim_timer3 as mgt3
from dlcp_fw.sim import manifests as mf
from dlcp_fw.sim import v30_symbols as vs
from dlcp_fw.sim.v30_symbols import load_gpasm_symbols_for_hex


@pytest.fixture(autouse=True)
def _clear_symbol_cache():
    load_gpasm_symbols_for_hex.cache_clear()
    yield
    load_gpasm_symbols_for_hex.cache_clear()


def test_load_gpasm_symbols_for_hex_returns_none_for_unusable_listing(tmp_path: Path) -> None:
    hex_path = tmp_path / "copied.hex"
    hex_path.write_text(":00000001FF\n", encoding="ascii")
    hex_path.with_suffix(".lst").write_text(
        "plain gpasm listing without symbol table\n",
        encoding="ascii",
    )

    assert load_gpasm_symbols_for_hex(hex_path) is None


def test_assemble_v30_prefers_fresh_output_listing_over_stale_source_listing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    asm_path = tmp_path / "toy.asm"
    asm_path.write_text("processor 18f2455\n", encoding="ascii")
    stale_source_lst = asm_path.with_suffix(".lst")
    stale_source_lst.write_text("STALE SOURCE LISTING\n", encoding="ascii")

    output_hex = tmp_path / "out.hex"
    copied_lst = tmp_path / "copied.lst"

    def fake_run(cmd, capture_output, text, check, cwd):
        output_hex.write_text(":00000001FF\n", encoding="ascii")
        output_hex.with_suffix(".lst").write_text(
            "FRESH OUTPUT LISTING\nhid_cmd_diag_memread:\n",
            encoding="ascii",
        )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(vs.subprocess, "run", fake_run)

    vs.assemble_v30(asm_path, output_hex, output_lst=copied_lst)

    assert copied_lst.read_text(encoding="ascii") == (
        "FRESH OUTPUT LISTING\nhid_cmd_diag_memread:\n"
    )


def test_resolve_main_an0_boot_exit_addr_falls_back_when_symbol_missing(monkeypatch) -> None:
    monkeypatch.setattr(mg, "load_gpasm_symbols_for_hex", lambda path: {})
    monkeypatch.setattr(
        mg,
        "_require_code_signature_addr",
        lambda main_hex, *, name, signature: 0x3456,
    )

    assert mg.resolve_main_an0_boot_exit_addr(Path("copied.hex")) == 0x3456


def test_resolve_main_cmd03_dispatch_addrs_falls_back_with_partial_symbols(monkeypatch) -> None:
    monkeypatch.setattr(
        mg,
        "load_gpasm_symbols_for_hex",
        lambda path: {"flow_main_uart_service_1be6_1bea": 0x1111},
    )
    fallback = {
        "cmd03 label003 break": 0x2222,
        "cmd03 return break": 0x3333,
        "cmd03 dispatch entry": 0x4444,
    }
    monkeypatch.setattr(
        mg,
        "_require_code_signature_addr",
        lambda main_hex, *, name, signature: fallback[name],
    )

    resolved = mg._resolve_main_cmd03_dispatch_addrs(
        main_hex=Path("copied.hex"),
        parser_break_addr=None,
        label003_break_addr=None,
        return_break_addr=None,
        dispatch_entry_pc=None,
    )

    assert resolved == (0x1111, 0x2222, 0x3333, 0x4444)


def test_timer3_harness_resolution_falls_back_when_symbol_missing(monkeypatch) -> None:
    seen: list[str] = []

    monkeypatch.setattr(mgt3, "load_gpasm_symbols_for_hex", lambda path: {})
    monkeypatch.setattr(mgt3, "_resolve_main_parser_break_addr", lambda *args, **kwargs: 0x1111)
    monkeypatch.setattr(
        mgt3,
        "_require_code_signature_addr",
        lambda main_hex, *, name, signature: seen.append(name) or 0x2222,
    )
    monkeypatch.setattr(
        mgt3,
        "build_seeded_main_sim_hex",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("stop after resolution")),
    )

    with pytest.raises(RuntimeError, match="stop after resolution"):
        mgt3.run_main_mailbox_gpsim_harness_timer3([], main_hex=Path("copied.hex"))

    assert seen == ["timer3 clear break"]


def test_chain_harness_mailbox_does_not_resolve_boot_exit(monkeypatch, tmp_path: Path) -> None:
    class FakeCliSession:
        def __init__(self, gpsim_bin: str) -> None:
            self.gpsim_bin = gpsim_bin

        def cmd(self, command: str, timeout_s: float = 10.0) -> str:
            return ""

    main_hex = tmp_path / "copied.hex"
    main_hex.write_text(":00000001FF\n", encoding="ascii")

    monkeypatch.setattr(cg, "require_gpsim_binary", lambda: "gpsim")
    monkeypatch.setattr(
        cg,
        "resolve_main_an0_boot_exit_addr",
        lambda path: (_ for _ in ()).throw(AssertionError("boot-exit resolver should not run")),
    )
    monkeypatch.setattr(cg, "build_seeded_main_sim_hex", lambda *args, **kwargs: args[1])
    monkeypatch.setattr(cg, "apply_overlays", lambda *args, **kwargs: None)
    monkeypatch.setattr(cg, "_CliSession", FakeCliSession)
    monkeypatch.setattr(cg.MainChainHarness, "_boot", lambda self: None)

    harness = cg.MainChainHarness(main_hex, transport_mode="mailbox")
    try:
        assert harness._main_boot_exit_addr is None
    finally:
        harness._tmp.cleanup()


def test_main_serial_mailbox_hooks_for_main_hex_falls_back_on_partial_symbols(monkeypatch) -> None:
    sentinel = object()

    monkeypatch.setattr(mf, "load_gpasm_symbols_for_hex", lambda path: {"rx_ring_read": 0x1234})
    monkeypatch.setattr(mf, "main_serial_mailbox_hooks", lambda gpasm="gpasm": sentinel)
    monkeypatch.setattr(
        mf,
        "main_serial_mailbox_hooks_dynamic",
        lambda symbols, gpasm="gpasm": (_ for _ in ()).throw(
            AssertionError("dynamic mailbox hooks should not be used")
        ),
    )

    assert mf.main_serial_mailbox_hooks_for_main_hex(Path("copied.hex")) is sentinel


def test_main_serial_mailbox_hooks_uart_only_for_main_hex_falls_back_on_partial_symbols(
    monkeypatch,
) -> None:
    sentinel = object()

    monkeypatch.setattr(mf, "load_gpasm_symbols_for_hex", lambda path: {"rx_ring_read": 0x1234})
    monkeypatch.setattr(mf, "main_serial_mailbox_hooks_uart_only", lambda gpasm="gpasm": sentinel)
    monkeypatch.setattr(
        mf,
        "main_serial_mailbox_hooks_uart_only_dynamic",
        lambda symbols, gpasm="gpasm": (_ for _ in ()).throw(
            AssertionError("dynamic UART-only mailbox hooks should not be used")
        ),
    )

    assert mf.main_serial_mailbox_hooks_uart_only_for_main_hex(Path("copied.hex")) is sentinel
