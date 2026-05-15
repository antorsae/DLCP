# V3.2 Sim Fault-Injection Sweep

Date: 2026-05-12

Scope: sim-only labelled stimuli against the canonical V3.2 MAIN release,
with V1.71 CONTROL included for USB-host and wake-window UART scenarios.

Artifacts:

- JSON: `artifacts/probes/v32_fault_injection_sweep/current.json`
- Markdown: `artifacts/probes/v32_fault_injection_sweep/current.md`

Command:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/sim_v32_fault_injection_sweep.py \
  --scenario all \
  --sweep-chunks 8,24 \
  --report-json artifacts/probes/v32_fault_injection_sweep/current.json \
  --report-md artifacts/probes/v32_fault_injection_sweep/current.md
```

Result: 14 scenario runs, elapsed wall time 61.16 s.

## Stimulus Labels

| Requested injection | Label | Model |
|---|---|---|
| permanent MSSP SEN stuck | `V32-SIM-INJECT-MSSP-SEN-STUCK` | Rust MSSP START fault with `start_busy_count=-1`. |
| permanent MSSP PEN stuck | `V32-SIM-INJECT-MSSP-PEN-STUCK` | Rust MSSP STOP fault with `stop_busy_count=-1`. |
| SCL held low | `V32-SIM-INJECT-I2C-SCL-LOW` | Rust MSSP physical SCL-low hold, plus RB1 low readback hold. |
| SDA held low | `V32-SIM-INJECT-I2C-SDA-LOW` | Rust MSSP physical SDA-low hold, plus RB0 low readback hold. |
| power-rail/BOR events | `V32-SIM-INJECT-POWER-RAIL-BOR` | AN0 rail sag, whole-chain BrownOut reboot, rail restore, firmware reconnect. |
| USB host polling while MAIN is stuck inside a firmware wait | `V32-SIM-INJECT-USB-POLL-WHILE-WAIT` | MAIN0 forced into SEN wait while `SimHidBackend` polls cmd `0x43` through the V3.2 firmware HID dispatcher. |
| high-rate UART bursts during the wake `GIE=0` window | `V32-SIM-INJECT-UART-BURST-WAKE-GIE0` | Native wake frame starts `adc_boot_gate`; raw MAIN0 EUSART burst is injected after a MAIN0 PC hit inside `adc_boot_gate`. |

## Findings

- SEN-stuck, PEN-stuck, SCL-low, and SDA-low all stalled V3.2 in the
  preset-apply wait shape for both 8- and 24-chunk sweeps.  The follow-up
  preset-A frame remained unconsumed, so the main loop did not keep servicing
  the native RX ring under these permanent wait conditions.
- The SEN and SDA/SCL stimuli are now owned by the Rust MSSP peripheral:
  START/PEN busy bits stay busy through the peripheral state machine, and
  forced-low SCL/SDA prevents in-flight master sequences from completing.
- BOR/reboot/reconnect now runs on the full V1.71 CONTROL + 2x V3.2 MAIN
  chain.  The sweep observes `RCON.BOR` cleared during the low-rail window,
  V3.2 Tier-1 `diag_reset_bor=1`, and CONTROL returning to the Volume screen
  after AN0 restore.
- USB cmd `0x43` polling returned OK while MAIN0 was held in an SEN wait via
  the firmware HID path: `SimHidBackend` stages a configured EP1 report,
  executes V3.2 `main_usb_service_3a26` / `hid_command_dispatch`, and reads
  the EP1 IN buffer.  Remaining limitation: this is dispatcher-boundary
  injection, not full USB SIE interrupt preemption while the app PC is pinned
  in the wait.
- Wake-window UART bursts were dropped by the silicon EUSART gate while V3.2
  had RX quiesced (`accepted=0`, `dropped=60` for both 8- and 24-chunk
  sweeps).  The burst is now anchored to a MAIN0 PC hit in the `adc_boot_gate`
  range (`0x2900..0x2944`), and the post-restore PC pass through the UART
  re-enable range was observed with `RCSTA=0x90`.

## Follow-Ups

- Couple the forced-low I2C line state into GPIO output readback if we need
  bitbang bus-clear tests to observe an externally held line even while the
  firmware temporarily drives the pin as an output.
- Model full USB SIE interrupt preemption if we need to prove USB liveness
  while the app PC remains pinned inside a blocking firmware wait without the
  dispatcher-boundary injection used by the current harness.
