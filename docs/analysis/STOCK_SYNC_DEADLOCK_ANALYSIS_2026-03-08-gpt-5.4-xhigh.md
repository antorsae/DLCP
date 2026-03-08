# Stock DLCP 2.3 / Control 1.4 Sync-Deadlock Analysis

Date: 2026-03-08
Scope: stock MAIN `DLCP Firmware V2.3.hex` and stock CONTROL `DLCP Control Firmware V1.4.hex`

## Executive Summary

Yes: the stock firmware contains multiple concrete bugs and design flaws that can plausibly explain random hangs, lost sync, and permanent `WAITING FOR DLCP` states.

The strongest findings are:

1. CONTROL has explicit forever-wait loops with no timeout or recovery.
2. CONTROL and MAIN both use circular RX software buffers with no full-state handling.
3. MAIN contains multiple unbounded blocking waits in serial and I2C paths.
4. Neither MCU has an effective watchdog recovery path in stock firmware.
5. CONTROL `V1.4`/`V1.5b` generates a very heavy periodic full-sync burst, which increases pressure on already fragile transport code.

These are sufficient to create the failure pattern you described:

- MAIN stops acting on commands such as volume changes.
- CONTROL eventually falls back to `WAITING FOR DLCP`.
- In multi-unit chains, one stuck MAIN can wedge the upstream path and strand CONTROL.

## Key Evidence

### 1) CONTROL has two intentional infinite wait loops

In stock `V1.4`, boot and reconnect both spin forever until the MAIN updates state:

- Boot wait loop: `label_204 @ 0x11DE`
- Reconnect wait loop: `label_216 @ 0x130A`

Boot wait (`0x11DE..0x1216`) repeatedly:

- sends `B1 04 00` via `function_029 @ 0x0BD6`
- delays
- calls RX parser `function_019 @ 0x044A`
- loops until all of `0x0B8`, `0x0B9`, `0x0A7`, `0x0A1` are no longer `0x80`

Reconnect wait (`0x130A..0x131A`) repeatedly:

- sends the same status poll
- delays
- parses RX
- loops until `0x1F.bit1` becomes set

There is no timeout, retry budget, UART reset, or fail-open path.

### 2) CONTROL periodically emits a very large sync burst

`function_028 @ 0x0B52` is the periodic full-sync sender. In `V1.4` it emits:

- 6 channel config frames
- link-address frame
- volume
- input
- mute
- timeout
- standby

This is 47 three-byte protocol packets per cycle, with small inter-frame delays.

`function_042 @ 0x0D24` can invoke this even while reconnect behavior is already in progress.

This matters because the transport has no flow control and weak buffer handling.

### 3) CONTROL RX ring buffer has a classic full/empty bug

CONTROL RX ISR:

- stores bytes at `0x066 + 0x99` in `0x3FC..0x412`
- increments write pointer `0x99`
- wraps after `0x30`

Foreground parser `function_019 @ 0x044A` treats:

- `0x99 == 0x98` as "buffer empty"

There is no software full check.

If the write pointer laps the read pointer, unread data is overwritten and the queue becomes indistinguishable from empty.

That can silently drop required status bytes such as:

- `cmd 0x03` standby/mute state
- `cmd 0x05` volume
- `cmd 0x06` source
- `cmd 0x07` input
- `cmd 0x1D` timeout

Missing any of these can keep CONTROL in `WAITING FOR DLCP`.

### 4) CONTROL TX enqueue can hard-freeze locally

`function_020 @ 0x0608` enqueues into the TX ring and enables `TXIE`.

If the ring would become full while TX interrupt draining is already active, it busy-waits at:

- `0x0628..0x062E`

There is no timeout and no watchdog service.

If TX draining ever stops, CONTROL can hang inside its own sender.

### 5) MAIN RX ring buffer has the same full/empty bug

MAIN RX ISR:

- `0x3B5C..0x3B8C`
- stores `RCREG` into `0x200 + 0xC7`
- increments `0xC7`
- wraps after `0xBF`

Foreground empty test:

- `function_109 @ 0x4872`
- only checks `0xC7 != 0xC6`

Foreground dequeue:

- `function_087 @ 0x45FA`

Again, there is no software full state.

If `0xC7` laps `0xC6`, unread serial bytes are overwritten and the queue looks empty. On a 3-byte protocol, losing one byte is enough to destroy alignment until the next recognizable header.

This is a strong candidate for "volume command ignored" incidents.

### 6) MAIN has multiple unbounded blocking waits

Strongest hard-stop sites:

- `function_111 @ 0x4896`: waits forever for `TXSTA.TRMT`
- `function_113 @ 0x48B6`: waits forever for I2C engine idle
- `function_056 @ 0x3E68`: waits forever on `PIR1.SSPIF` / `SSPSTAT.BF`
- `function_072 @ 0x4368`: waits forever on `SSPCON2.SEN/PEN`
- `function_093 @ 0x46BA`: same style unbounded I2C wait

MAIN command handling is cooperative, not ISR-dispatched:

- main loop: `0x48CA`
- service function: `function_102 @ 0x47CE`
- serial parser: `function_006 @ 0x1BE6`

So if MAIN blocks in one of the I2C or TX waits, it stops servicing incoming control commands entirely.

### 7) MAIN can explicitly disable RX

At `0x13BA`, MAIN clears `RCSTA.CREN`, resets serial state, and clears both ring indices.

Re-enable is not local to that path; recovery depends on later code reaching:

- UART init `0x4570`
- OERR recovery `0x3B84`
- `function_126 @ 0x495E`

If that recovery path is missed, serial receive remains dead.

### 8) No effective watchdog on either MCU

MAIN stock config:

- `CONFIG WDT = OFF`
- `CONFIG WDTPS = 32768`
- `CONFIG STVREN = OFF`

CONTROL stock config bytes:

- `CONFIG2H = 0x00`
- `CONFIG4L = 0x80`

Per `39632e.txt`:

- `WDTEN = 0` means watchdog is disabled unless software sets `WDTCON.SWDTEN`
- `STVREN = 0` means stack full/underflow does not reset

Observed stock behavior:

- no application writes to `WDTCON.SWDTEN`
- CONTROL does not use `CLRWDT`
- MAIN has reachable `CLRWDT` only in helper paths, but watchdog is not enabled

Net effect: if either MCU wedges in a hard loop, it stays wedged.

## Simulator Findings

These runs were useful, but they do not fully reproduce raw hardware because the gpsim harnesses patch reset and mailbox behavior.

### Direct stock CONTROL-only LCD decode

Command:

```bash
.venv_ep0/bin/python scripts/gpsim_lcd_capture_decode.py --hex firmware/stock/control/'DLCP Control Firmware V1.4.hex' --cycles 50000000
```

Result:

- final LCD: `Waiting for DLCP`

This confirms bare stock CONTROL naturally parks at the waiting screen without a cooperating MAIN.

### Stock co-sim boot script

Command:

```bash
.venv_ep0/bin/python scripts/test_full_boot.py
```

Observed:

- `Firmware V1.4`
- `Waiting for DLCP`
- then `Volume: / -96.0dB`

Important caveat: this script injects synthetic heartbeat/progress to let the boot path complete.

### Stock headless chain diagnose, current harness

Single-main 8s:

```bash
.venv_ep0/bin/python scripts/gpsim_headless_chain_diagnose.py firmware/stock/control/'DLCP Control Firmware V1.4.hex' --main-hex firmware/stock/main/'DLCP Firmware V2.3.hex' --single-main --fast-boot --duration-s 8 --chunk-cycles 50000 --main-chunk-cycles 50000 --output artifacts/sim/current/headless_single_main_stock_8s.json
```

Observed:

- warmup reached `Volume: / -96.0dB`
- `bit1_events = 0`
- `M0->CTL overrun_total = 348`

Two-main 8s:

```bash
.venv_ep0/bin/python scripts/gpsim_headless_chain_diagnose.py firmware/stock/control/'DLCP Control Firmware V1.4.hex' --main-hex firmware/stock/main/'DLCP Firmware V2.3.hex' --fast-boot --duration-s 8 --chunk-cycles 50000 --main-chunk-cycles 50000 --output artifacts/sim/current/headless_two_main_stock_8s.json
```

Observed:

- warmup reached `Volume: / -96.0dB`
- `bit1_events = 0`
- no link overruns in that short run

Interpretation:

- current wrappers are now good enough to reach stable display in short runs
- but they do not invalidate the static bug findings above
- and they do not fully model raw stock reconnect failure because the harness applies support patches

## Likely Real-World Failure Mechanisms

Most likely causes of your observed random hangs:

1. MAIN blocks in an unbounded I2C wait during DSP or side-device traffic.
2. MAIN RX ring overruns or desynchronizes under burst traffic and stops accepting commands.
3. CONTROL RX ring drops a needed status field, leaving the wait-state sentinels stuck.
4. In a chain, an upstream MAIN blocks in synchronous forwarding TX and strands downstream communication.
5. Because watchdog recovery is absent, any of the above becomes permanent until power-cycle.

## Relation To Later Stock CONTROL Versions

From disassembly comparison:

- `V1.5b` keeps the same UART transport and same unbounded wait structure.
- `V1.6b` still lacks true timeout/recovery logic.
- `V1.6b` does reduce periodic sync load significantly versus `V1.4`/`V1.5b`.

So later stock CONTROL versions do not look like a real deadlock fix, though `V1.6b` is probably less self-stressing on the link.

## Recommended Fix Order

If the goal is to build a practical patched firmware, the best order is:

1. Add bounded timeout + UART reinit to CONTROL wait loops.
2. Add RX ring full detection on both CONTROL and MAIN.
3. Add timeout + recovery around MAIN `function_111` TX waits.
4. Add timeout + recovery around MAIN I2C waits.
5. Reduce or gate CONTROL periodic full-sync traffic.
6. Only then consider enabling watchdog recovery.

Reason:

- watchdog alone would only turn silent deadlocks into resets
- it would not prevent sync corruption or queue-loss bugs
- bounded waits plus explicit recovery make watchdog integration much safer

## Concrete Patch Targets

CONTROL:

- wait loops: `0x11DE`, `0x130A`
- RX ISR ring handling: `0x03FC..0x0412`
- parser empty check: `0x0456`
- TX enqueue full wait: `0x0628..0x062E`
- periodic full-sync: `0x0B52`

MAIN:

- RX ISR ring handling: `0x3B5C..0x3B8C`
- empty check: `0x4872`
- dequeue: `0x45FA`
- TX blocking send: `0x4896`
- I2C idle/wait helpers: `0x48B6`, `0x3E68`, `0x4368`, `0x46BA`
- RX disable site: `0x13BA`

## Bottom Line

The stock firmware is not just "missing robustness"; it contains specific protocol and wait-state bugs that can plausibly produce exactly the hangs you see.

The two highest-confidence root causes are:

- no timeout/recovery in CONTROL wait paths
- no full-state handling in both UART software rings

The two highest-impact MAIN-side freeze risks are:

- unbounded I2C waits
- unbounded TX wait with watchdog disabled

Those are the first areas to patch.
