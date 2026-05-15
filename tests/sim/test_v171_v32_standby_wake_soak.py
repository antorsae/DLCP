from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from dlcp_fw.paths import PROJECT_ROOT


def _load_soak_module():
    scripts_dir = PROJECT_ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    path = scripts_dir / "sim_v171_v32_standby_wake_soak.py"
    spec = importlib.util.spec_from_file_location("sim_v171_v32_standby_wake_soak", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_soak_defaults_enable_recoverable_fault_suite() -> None:
    soak = _load_soak_module()
    args = soak.build_arg_parser().parse_args(["--seconds", "1"])
    assert args.faults == soak.DEFAULT_FAULTS
    assert args.fault_every_cycles == 1
    assert args.brownout_every_s == 0.0
    assert args.mssp_quiesce_tcy > args.fault_recovery_tcy
    assert args.mssp_quiesce_step_tcy > 0
    assert "usb_poll_while_wait" in args.faults
    assert "power_rail_bor" in args.faults
    assert "uart_burst_wake_gie0" in args.faults


def test_soak_fault_parser_supports_all_none_and_dedupe() -> None:
    soak = _load_soak_module()
    assert soak._parse_faults("none") == ()
    assert soak._parse_faults("") == ()
    assert soak._parse_faults("dsp_addr_nack,dsp_addr_nack") == ("dsp_addr_nack",)
    assert soak._parse_faults("all") == soak.DEFAULT_FAULTS


def test_soak_no_faults_alias_restores_pure_soak_mode() -> None:
    soak = _load_soak_module()
    args = soak.build_arg_parser().parse_args(["--seconds", "1", "--no-faults"])
    assert args.faults == ()


def test_soak_periodic_brownout_parser_enables_time_cadence() -> None:
    soak = _load_soak_module()
    args = soak.build_arg_parser().parse_args(["--seconds", "120", "--brownout-every-s", "60"])
    assert args.brownout_every_s == 60.0
    cadence = soak.PeriodicBrownout.from_seconds(args.brownout_every_s)
    assert cadence.enabled
    assert cadence.every_ticks == 60 * soak.TICKS_PER_SEC
    assert cadence.next_tick == 60 * soak.TICKS_PER_SEC


def test_soak_progress_prefix_distinguishes_injection_from_failure() -> None:
    soak = _load_soak_module()
    source = Path(soak.__file__).read_text(encoding="utf-8")
    assert " INJECT_OK " in source
    assert " FAULT {_format_fault_result" not in source


def test_sim_timeline_survives_whole_chain_tick_rewind() -> None:
    soak = _load_soak_module()

    class FakeChain:
        def __init__(self) -> None:
            self.tick = 100

        def current_tick(self) -> int:
            return self.tick

    fake = FakeChain()
    timeline = soak.SimTimeline.start(fake)
    fake.tick = 150
    assert timeline.sync() == 50
    fake.tick = 20
    assert timeline.sync() == 70
    fake.tick = 35
    assert timeline.sync() == 85


def test_periodic_brownout_scheduler_injects_during_awake_idle(monkeypatch, capsys) -> None:
    soak = _load_soak_module()

    class FakeChain:
        def __init__(self) -> None:
            self.tick = 0
            self.steps: list[int] = []

        def current_tick(self) -> int:
            return self.tick

        def step_ticks(self, ticks: int) -> None:
            self.steps.append(ticks)
            self.tick += ticks

    fake = FakeChain()
    timeline = soak.SimTimeline.start(fake)
    cadence = soak.PeriodicBrownout.from_seconds(60)
    stats = soak.FaultStats()
    calls: list[tuple[int, int]] = []

    def fake_bor(chain, start_tick, args, *, cycle):  # noqa: ANN001
        calls.append((cycle, chain.current_tick()))
        chain.step_ticks(5 * soak.TICKS_PER_SEC)
        return {"name": "power_rail_bor", "reconnect_chunks": 3}

    monkeypatch.setattr(soak, "_exercise_power_rail_bor", fake_bor)
    args = soak.build_arg_parser().parse_args(
        ["--seconds", "180", "--brownout-every-s", "60", "--fault-log-every", "1"]
    )

    soak._step_awake_idle_with_periodic_brownouts(
        fake,
        timeline,
        0,
        args,
        idle_ticks=130 * soak.TICKS_PER_SEC,
        brownout=cadence,
        fault_stats=stats,
        cycle=7,
    )

    assert calls == [
        (7, 60 * soak.TICKS_PER_SEC),
        (7, 120 * soak.TICKS_PER_SEC),
    ]
    assert stats.counts == {"power_rail_bor": 2}
    assert timeline.sync() == 130 * soak.TICKS_PER_SEC
    assert cadence.next_tick == 180 * soak.TICKS_PER_SEC
    out = capsys.readouterr().out
    assert "INJECT_OK periodic_brownout power_rail_bor reconnect_chunks=3" in out


def test_mssp_recovery_wait_tolerates_transient_transfer_bits() -> None:
    soak = _load_soak_module()

    class FakeChain:
        def __init__(self) -> None:
            self.sspcon2_values = [0x24, 0x24, 0x20]
            self.sspcon2_index = 0
            self.steps: list[int] = []

        def read_main_reg(self, unit: int, addr: int) -> int:
            if addr == soak.SSPCON2:
                value = self.sspcon2_values[
                    min(self.sspcon2_index, len(self.sspcon2_values) - 1)
                ]
                self.sspcon2_index += 1
                return value
            if addr == soak.MAIN_RX_RING_RD or addr == soak.MAIN_RX_RING_WR:
                return 0
            if addr == soak.MAIN_ACTIVE_FLAGS:
                return 0x08
            if addr == soak.MAIN_LATB:
                return 0x18
            if addr == soak.MAIN_LATA:
                return 0x40
            return 0

        def step_tcy(self, ticks: int) -> None:
            self.steps.append(ticks)

        def is_connected(self) -> bool:
            return True

        def is_waiting(self) -> bool:
            return False

        def lcd_lines(self) -> tuple[str, str]:
            return ("Volume:-17.0dB A", "Auto Detect     ")

    fake = FakeChain()
    soak._assert_main0_recovered(
        fake,
        0,
        "transient",
        mssp_quiesce_tcy=50,
        mssp_quiesce_step_tcy=10,
    )
    assert fake.steps == [10, 10]


def test_mssp_recovery_wait_reports_persistent_transfer_bits() -> None:
    soak = _load_soak_module()

    class FakeChain:
        def __init__(self) -> None:
            self.steps: list[int] = []

        def read_main_reg(self, unit: int, addr: int) -> int:
            if addr == soak.SSPCON2:
                return 0x04
            if addr == soak.MAIN_RX_RING_RD or addr == soak.MAIN_RX_RING_WR:
                return 0
            if addr == soak.MAIN_ACTIVE_FLAGS:
                return 0x08
            if addr == soak.MAIN_LATB:
                return 0x18
            if addr == soak.MAIN_LATA:
                return 0x40
            return 0

        def step_tcy(self, ticks: int) -> None:
            self.steps.append(ticks)

        def current_tick(self) -> int:
            return sum(self.steps)

        def is_connected(self) -> bool:
            return True

        def is_waiting(self) -> bool:
            return False

        def lcd_lines(self) -> tuple[str, str]:
            return ("Volume:-17.0dB A", "Auto Detect     ")

    fake = FakeChain()
    try:
        soak._assert_main0_recovered(
            fake,
            0,
            "persistent",
            mssp_quiesce_tcy=25,
            mssp_quiesce_step_tcy=10,
        )
    except soak.SoakFailure as exc:
        details = exc.args[0]
    else:  # pragma: no cover
        raise AssertionError("persistent MSSP transfer bits should fail")

    assert fake.steps == [10, 10, 5]
    assert details["label"] == "persistent"
    assert "did not quiesce" in details["message"]
    assert "0x04" in details["message"]
