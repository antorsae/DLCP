#!/usr/bin/env python3
"""V1.71 Layer 2 chain-test diagnostic probe.

Mirrors the two V3.2 wire-chain scenarios that broke under V1.64b
CONTROL even after Layer 2 landed:

  * interleaved_mute  — IR mute injected during a delayed preset switch
  * preset_soak       — alternating A↔B preset cycles with standby/wake

Prints rich per-step state (preset, mute, active, RX ring, CONTROL LCD,
v171_full_sync_step) every N chain steps so we can tell whether each
convergence is *slow but eventual* (limit just needs to be bigger) or
*genuinely stuck* (Layer 2 is missing something).

Usage::

    .venv_ep0/bin/python scripts/probe_v171_layer2_chain.py [interleaved_mute|preset_soak|both]
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from dlcp_fw.paths import PATCHED_CONTROL_HEX_V164B, V32_MAIN_HEX
from dlcp_fw.sim.control_gpsim import _read_reg
from dlcp_fw.sim.wire_chain_gpsim import WireMultiMainChainHarness


_STATUS_5E = 0x05E
_PRESET_JOB_STATE = 0x2DE
_RX_RING_RD = 0x0C6
_RX_RING_WR = 0x0C7
_PRESET_B_BIT = 0x04
_ACTIVE_BIT = 0x08
_MUTE_BIT = 0x10
V171_FULL_SYNC_STEP_PHYS = 0x170


def _main_status(chain: WireMultiMainChainHarness, idx: int) -> int:
    return _read_reg(chain.mains[idx]._issue, _STATUS_5E)


def _dump_state(chain: WireMultiMainChainHarness, label: str, step_no: int) -> None:
    states = []
    for idx, m in enumerate(chain.mains):
        st = _main_status(chain, idx)
        job = _read_reg(m._issue, _PRESET_JOB_STATE)
        rx_rd = _read_reg(m._issue, _RX_RING_RD)
        rx_wr = _read_reg(m._issue, _RX_RING_WR)
        preset = 1 if (st & _PRESET_B_BIT) else 0
        active = 1 if (st & _ACTIVE_BIT) else 0
        muted = 1 if (st & _MUTE_BIT) else 0
        states.append(
            f"main{idx}(st=0x{st:02X} preset={preset} active={active} muted={muted} "
            f"job=0x{job:02X} rx={rx_rd:02X}->{rx_wr:02X})"
        )
    fs_step = _read_reg(chain.control._issue, V171_FULL_SYNC_STEP_PHYS)
    lcd = chain.lcd_lines()
    waiting = "Y" if chain.is_waiting() else "n"
    print(
        f"[{label} step={step_no:4d}] waiting={waiting} fs_step={fs_step} "
        f"lcd={lcd[0]!r:18s} | " + " ".join(states)
    )


def _new_chain(*, fast_boot: bool) -> WireMultiMainChainHarness:
    return WireMultiMainChainHarness(
        PATCHED_CONTROL_HEX_V164B,
        V32_MAIN_HEX,
        main_units=2,
        fast_boot=fast_boot,
        disable_standby_check=False,
    )


def _set_profile_hypex(chain: WireMultiMainChainHarness) -> None:
    for reg, val in (
        (0x020, 0x10), (0x021, 0x32), (0x022, 0x33), (0x023, 0x34),
        (0x024, 0x36), (0x025, 0x37), (0x026, 0x35),
    ):
        chain.control._issue(f"reg(0x{reg:03X})={val:#04x}", 5.0)


def _enter_standby_via_ir(chain: WireMultiMainChainHarness, *, label: str) -> None:
    for attempt in range(3):
        chain.control.inject_decoded_ir_event(cmd=0x32, addr=0x10, steps=1)
        for i in range(30):
            chain.step()
            lcd = chain.lcd_lines()[0].upper()
            if "ZZZ" in lcd:
                print(f"[{label}] entered standby after attempt {attempt+1}, step {i+1}")
                return
    print(f"[{label}] FAILED to enter standby after 3 attempts")


def _wake_via_ir(chain: WireMultiMainChainHarness, *, label: str, limit: int = 200) -> None:
    chain.control.inject_decoded_ir_event(cmd=0x32, addr=0x10, steps=1)
    last = chain.run_until_connected(limit=limit)
    if last is None:
        print(f"[{label}] wake produced no steps")
    elif chain.is_waiting():
        print(f"[{label}] still WAITING after wake")
    else:
        print(f"[{label}] reconnected; lcd={chain.lcd_lines()[0]!r}")


def _wait_until(
    chain: WireMultiMainChainHarness,
    *,
    label: str,
    limit: int,
    dump_every: int,
    converged_pred,
) -> bool:
    saw_non_idle = False
    for i in range(limit):
        if chain.is_waiting():
            chain.run_until_connected(limit=120)
        chain.step()
        if any(_read_reg(m._issue, _PRESET_JOB_STATE) != 0 for m in chain.mains):
            saw_non_idle = True
        if (i % dump_every) == 0:
            _dump_state(chain, label, i)
        if converged_pred():
            print(f"[{label}] CONVERGED at step {i+1}/{limit} (saw_non_idle={saw_non_idle})")
            return True
    _dump_state(chain, label + ".TIMEOUT", limit)
    print(f"[{label}] DID NOT CONVERGE within {limit} steps (saw_non_idle={saw_non_idle})")
    return False


def probe_interleaved_mute() -> int:
    print("\n=== probe: interleaved_mute ===")
    chain = _new_chain(fast_boot=True)
    try:
        chain.run_until_connected(limit=100)
        _set_profile_hypex(chain)
        _dump_state(chain, "after-profile", 0)

        # Public-key path: press R (preset menu), then D (preset B).
        chain.press("R")
        chain.step()
        chain.press("D")
        chain.step()
        chain.step()
        _dump_state(chain, "after-preset-press", 0)

        # Wait for main0 preset_job to reach non-IDLE state.
        for i in range(60):
            chain.step()
            if _read_reg(chain.mains[0]._issue, _PRESET_JOB_STATE) != 0:
                print(f"[interleaved_mute] main0 preset_job_active at step {i+1}/60")
                break

        # Inject IR mute during preset job.
        for attempt in range(3):
            chain.control.inject_decoded_ir_event(cmd=0x35, addr=0x10, steps=1)
            for i in range(16):
                chain.step()
                tx = chain.control.tx_frames()
                if any(f.route == 0xB0 and f.cmd == 0x03 and f.data in {0x02, 0x03} for f in tx[-10:]):
                    print(f"[interleaved_mute] mute IR delivered, attempt {attempt+1} step {i+1}")
                    break
            else:
                continue
            break

        ok = _wait_until(
            chain,
            label="preset_drain",
            limit=720,  # 120 * 6
            dump_every=60,
            converged_pred=lambda: all(_read_reg(m._issue, _PRESET_JOB_STATE) == 0 for m in chain.mains),
        )
        if not ok:
            return 1

        ok = _wait_until(
            chain,
            label="mute_converge",
            limit=480,  # 80 * 6
            dump_every=40,
            converged_pred=lambda: all((_main_status(chain, i) & _MUTE_BIT) for i in range(2)),
        )
        if not ok:
            return 2
        return 0
    finally:
        chain.close()


def probe_preset_soak() -> int:
    print("\n=== probe: preset_soak ===")
    chain = _new_chain(fast_boot=False)
    try:
        chain.run_until_connected(limit=100)
        _set_profile_hypex(chain)
        _dump_state(chain, "after-profile", 0)

        for cycle, target in enumerate((1, 0, 1), start=1):
            print(f"\n--- cycle {cycle}: target preset {target} ---")
            chain.control.inject_decoded_ir_event(cmd=0x39 if target else 0x38, addr=0x10, steps=1)
            chain.step()
            chain.step()
            ok = _wait_until(
                chain,
                label=f"cycle{cycle}.switch",
                limit=1320,  # 220 * 6
                dump_every=80,
                converged_pred=lambda t=target: (
                    [1 if (_main_status(chain, i) & _PRESET_B_BIT) else 0 for i in range(2)] == [t, t]
                    and all(_read_reg(m._issue, _PRESET_JOB_STATE) == 0 for m in chain.mains)
                ),
            )
            if not ok:
                return 10 + cycle

            _enter_standby_via_ir(chain, label=f"cycle{cycle}.standby")
            _wake_via_ir(chain, label=f"cycle{cycle}.wake")
            _dump_state(chain, f"cycle{cycle}.post-wake", 0)

            ok = _wait_until(
                chain,
                label=f"cycle{cycle}.post-wake-reconcile",
                limit=1320,
                dump_every=80,
                converged_pred=lambda t=target: (
                    [1 if (_main_status(chain, i) & _PRESET_B_BIT) else 0 for i in range(2)] == [t, t]
                ),
            )
            if not ok:
                return 20 + cycle
        return 0
    finally:
        chain.close()


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    rc = 0
    if which in ("interleaved_mute", "both"):
        rc = probe_interleaved_mute() or rc
    if which in ("preset_soak", "both"):
        rc = probe_preset_soak() or rc
    return rc


if __name__ == "__main__":
    sys.exit(main())
