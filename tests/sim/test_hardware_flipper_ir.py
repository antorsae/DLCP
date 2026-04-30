from __future__ import annotations

import json

import pytest

from dlcp_fw.cli import hardware_flipper_ir as ir


# All tests in this module are backend-agnostic (Python-level
# behavioral models, hex/source byte comparisons, flash-tool plumbing,
# scenario runners).  No gpsim runtime, no rust facade.  Mark the
# whole module dual_supported so DLCP_SIM_BACKEND={rust,dual} does
# not auto-skip them.
pytestmark = pytest.mark.dual_supported


def test_discover_flipper_serial_ports_filters_real_flipper_like_nodes(monkeypatch) -> None:
    monkeypatch.setattr(
        ir.Path,
        "glob",
        lambda self, pattern: [
            ir.Path("/dev/cu.NicksLugs"),
            ir.Path("/dev/cu.debug-console"),
            ir.Path("/dev/cu.usbmodemflip_Ovarlide1"),
            ir.Path("/dev/cu.FlipperZero"),
        ],
    )

    ports = ir.discover_flipper_serial_ports()

    assert ports == ["/dev/cu.FlipperZero", "/dev/cu.usbmodemflip_Ovarlide1"]


def test_resolve_action_spec_supports_hypex_profile_actions_and_aliases() -> None:
    f2 = ir.resolve_action_spec("F2")
    power = ir.resolve_action_spec("power")
    standby = ir.resolve_action_spec("standby")
    wake = ir.resolve_action_spec("wake")
    mute = ir.resolve_action_spec("mute")

    assert (f2.protocol, f2.address, f2.command) == ("RC5", 0x10, 0x39)
    assert (power.protocol, power.address, power.command) == ("RC5", 0x10, 0x32)
    assert (standby.protocol, standby.address, standby.command) == ("RC5", 0x10, 0x3A)
    assert (wake.protocol, wake.address, wake.command) == ("RC5", 0x10, 0x3B)
    assert (mute.protocol, mute.address, mute.command) == ("RC5", 0x10, 0x35)


def test_send_ir_action_formats_flipper_cli_command_and_returns_port(monkeypatch) -> None:
    monkeypatch.setattr(ir, "resolve_flipper_serial_port", lambda *, port=None: "/dev/cu.usbmodemflip_Ovarlide1")
    monkeypatch.setattr(
        ir,
        "issue_cli_command",
        lambda port, command, timeout_s, idle_s: ">: ir tx RC5 10 39\r\n>:\r\n",
    )

    payload = ir.send_ir_action(action="F2")

    assert payload["canonical_action"] == "F2"
    assert payload["cli_command"] == "ir tx RC5 10 39"
    assert payload["port"] == "/dev/cu.usbmodemflip_Ovarlide1"


def test_main_prints_json_for_supported_action(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        ir,
        "send_ir_action",
        lambda **kwargs: {
            "action": "F2",
            "canonical_action": "F2",
            "protocol": "RC5",
            "address_hex": "10",
            "command_hex": "39",
            "port": "/dev/cu.usbmodemflip_Ovarlide1",
            "cli_command": "ir tx RC5 10 39",
            "raw_response": "",
            "clean_response": "",
        },
    )

    rc = ir.main(["--action", "F2"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["cli_command"] == "ir tx RC5 10 39"


def test_unknown_action_raises() -> None:
    with pytest.raises(RuntimeError, match="unknown IR action"):
        ir.resolve_action_spec("banana")
