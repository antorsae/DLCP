# Proposal 1 SRC4382 USB Diagnostics V1a Raw-Read IMPL

Date: 2026-06-20
Status: Implemented in MAIN V3.5 source; simulator verified; live hardware not exercised by this change
Source spec: `docs/PROPOSAL_1_SRC4382_USB_DIAGNOSTICS_SPEC.md`

## Scope

V1a is now a compact USB operator diagnostic, not a firmware snapshot service.
MAIN USB `cmd 0x45` reads exactly one requested SRC4382 page-0 register and
returns the raw byte.  The host script performs the multi-register read list,
assembles the human-readable snapshot, and prints the ASCII tables.

No CONTROL/LCD/current-loop work is included.  No SRC4382 writes, page flips,
firmware register whitelist, firmware decode, cooperative job, persistent cache,
or cmd45 RAM allocation are included.

## Raw ABI

Request:

```text
byte 0: 0x45
byte 1: SRC4382 page-0 register address
byte 2..63: ignored
```

Response:

```text
byte 0: 0x45
byte 1: status       0=OK, 1=I2C failure
byte 2: register echo
byte 3: value        0xFF on failure
byte 4..63: reserved, currently zero
```

Operator command:

```bash
.venv_ep0/bin/python scripts/dlcp_src4382_diag.py
```

Ratio and PC/PD reads are host defaults now; the older
`--include-ratio --include-pc-pd` flags are not needed for normal operator use.

## Host Read Set

The default host snapshot reads:

- Clock/status: `0x03`, `0x04`, `0x05`, `0x06`, `0x07`, `0x09`, `0x0A`, `0x0E`
- Route/payload/lock/errors: `0x08`, `0x0D`, `0x12`, `0x13`, `0x14`, `0x15`
- SRC config: `0x2D`, `0x2E`, `0x2F`
- Ratio: `0x32`, then `0x33` as two separate transactions
- PC/PD: `0x29`, `0x2A`, `0x2B`, `0x2C` as four separate transactions

There is intentionally no firmware-side whitelist.  Tests prove byte 1 and
padding are not validated as a higher-level request shape; this keeps MAIN small
and lets operator tooling query one-off page-0 registers such as `0x7F`.

## MAIN Implementation

Changed `src/dlcp_fw/asm/dlcp_main_v35.asm`:

- Extended HID dispatch so `cmd 0x45` branches to `hid_src4382_diag_dispatch`.
- Added a small raw-read handler that stages `[0x45, status, reg, value]` into
  the EP1 IN buffer.
- Added `src4382_cmd45_i2c_read_reg`, a bounded single-register random-read
  helper for SRC4382 address `0x71` (`0xE2` write, `0xE3` read).
- Added ACKSTAT handling by clearing and checking the existing
  `dsp_fault_flags.bit2` latch around each transmitted I2C byte.
- Attempts STOP on raw-read failure before returning status `1`.
- Uses only existing scratch bytes and the HID buffers.  No `cmd45_cache_*` or
  `cmd45_job_*` RAM remains in `dlcp_main_ram.inc` or `ram_bank_manifest.py`.

Local cmd45 firmware block size after the ACKSTAT/STOP path is under the
requested 200-word ceiling:

```text
hid_src4382_diag_dispatch..src4382_cmd45_i2c_pen_timeout:
  164 bytes / 82 PIC18 instruction words
```

## Host Implementation

Changed `src/dlcp_fw/flash/dlcp_src4382_diag.py` and
`scripts/dlcp_src4382_diag.py`:

- `make_cmd45_request(reg)` sends raw register reads.
- `parse_cmd45_raw_read_response()` validates the raw response.
- `query_src4382_snapshot()` performs the default multi-read sequence and
  assembles the existing `Src4382Snapshot` object on the host.
- The stdout table keeps the previous operator-friendly view:
  status, route, lock, payload, rate/ratio, clock evidence, RXCKR,
  SRC config, raw register table, PC/PD table, and errors.
- The JSON path still exposes raw register bytes plus decoded clock/status
  evidence.

Rate rules:

- The only fixed clock assumption is red/MCLK = 24 MHz.
- Exact output/frame rates are derived only from exposed Port A/B or DIT
  master-mode MCLK divider evidence.  `/256` under that condition is
  `93.750 kHz`.
- Ratio-derived input rates require both `0x32` and `0x33` plus a proven output
  rate basis.  `0x0A.READY` is displayed as mask-gated interrupt/status
  evidence, not used as a ratio-valid gate.

## Simulator Fix

Changed `crates/dlcp-sim/src/chain.rs` and `crates/dlcp-sim-py/src/lib.rs`:

- Added `Chain::dispatch_post_instruction_peripherals(core_idx)`.
- The Python-facing `firmware_hid_report()` harness now calls that hook after
  each inline firmware instruction.

Reason: normal chain execution dispatched MSSP I2C bus events after every
instruction, but `firmware_hid_report()` was stepping the HID handler inline and
bypassed that dispatch.  Without the hook, synchronous cmd45 I2C reads saw stale
`SSPBUF` values, typically the read address `0xE3`, instead of the SRC4382
slave-provided data byte.

Rebuild command used after the simulator patch:

```bash
PYO3_PYTHON="$PWD/.venv_ep0/bin/python" cargo build --release -p dlcp-sim-py
bash crates/dlcp-sim-py/build.sh
```

## Tests

Focused tests run during implementation:

```text
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_dlcp_src4382_diag.py
65 passed in 38.85s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_ram_bank_safety.py
19 passed in 0.93s

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target main-v35 --fix-aliases
RAM bank safety: OK (main-v35)
```

Final build and headroom evidence:

```text
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v35_release.py
built canonical V3.5 release: firmware/patched/releases/DLCP_Firmware_V3.5.hex
release rev 0x008E -> 0x008F

shasum -a 256 firmware/patched/releases/DLCP_Firmware_V3.5.hex
10820d98b96e34839fe434fb63882c9f0fa50c789aae7b4922a779e2423d8891

Program Memory Bytes Used: 18924
Program Memory Bytes Free:  5652
Contiguous free before preset_table_b at 0x4C00: 1826 bytes
```

Additional regression coverage:

```text
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v32_src4382_autodetect_polling.py
51 passed in 71.56s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_dlcp_diag.py tests/sim/test_v35_v173_release_builders.py
54 passed, 3 warnings in 0.21s

cargo test -p dlcp-sim --release
passed
```

## Review Notes

- Size: raw reads keep MAIN small; host code is the right place for the register
  list and decode.
- Safety: no page writes, no page-1 access, no arbitrary SRC writes.
- Robustness: NACK and timeout paths return a visible failure for that raw read
  instead of preserving stale cached values.
- Compatibility: older schema-1 parser tests remain because the host still
  accepts previously captured snapshot-shaped responses, but new firmware emits
  the raw ABI above.
