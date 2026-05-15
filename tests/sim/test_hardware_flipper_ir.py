from __future__ import annotations

import json

import pytest

from dlcp_fw.cli import hardware_flipper_ir as ir


# All tests in this module are backend-agnostic (Python-level
# behavioral models, hex/source byte comparisons, flash-tool plumbing,
# scenario runners).  No gpsim runtime, no rust facade.
# Mark the whole module dual_supported (legacy informational
# marker; see tests/sim/conftest.py for the post-PF.4 inert
# semantics).
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


def test_resolve_action_spec_supports_standard_rc5_profile_actions() -> None:
    power = ir.resolve_action_spec("std_power")
    mute = ir.resolve_action_spec("rc5_mute")
    vol_up = ir.resolve_action_spec("std_vol_up")
    vol_down = ir.resolve_action_spec("rc5_vol_down")
    input_up = ir.resolve_action_spec("std_ch_up")
    input_down = ir.resolve_action_spec("std_input_down")

    assert (power.protocol, power.address, power.command) == ("RC5", 0x00, 0x0C)
    assert (mute.protocol, mute.address, mute.command) == ("RC5", 0x00, 0x0D)
    assert (vol_up.protocol, vol_up.address, vol_up.command) == ("RC5", 0x00, 0x10)
    assert (vol_down.protocol, vol_down.address, vol_down.command) == ("RC5", 0x00, 0x11)
    assert (input_up.protocol, input_up.address, input_up.command) == ("RC5", 0x00, 0x20)
    assert (input_down.protocol, input_down.address, input_down.command) == ("RC5", 0x00, 0x21)


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


def test_send_ir_action_rejects_open_application_cli_error(monkeypatch) -> None:
    monkeypatch.setattr(
        ir,
        "resolve_flipper_serial_port",
        lambda *, port=None: "/dev/cu.usbmodemflip_Ovarlide1",
    )
    monkeypatch.setattr(
        ir,
        "issue_cli_command",
        lambda port, command, timeout_s, idle_s: (
            ">: ir tx RC5 10 39\r\n"
            "this command cannot be run while an application is open\r\n>:\r\n"
        ),
    )

    with pytest.raises(RuntimeError, match="cannot be run while an application is open"):
        ir.send_ir_action(action="F2")


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
