# V2.7 MAIN + V1.63b CONTROL — Specification

Date: 2026-03-27
Status: draft
Depends on: V2.6 MAIN + V1.62b CONTROL (committed)

## Scope

V2.7 addresses the remaining MSSP/I2C robustness gaps that V2.6
does not cover.  V1.63b adds CONTROL-side DSP fault visibility.

---

## V2.7 MAIN firmware

### Fix C: I2C bus-clear after MSSP recovery

**Problem**: `patch_recover_mssp` calls `function_101` (clrf SSPCON1,
clrf SSPCON2, re-enable SSPEN).  This resets the PIC's MSSP peripheral
but does NOT release a stuck I2C slave.  If the TAS3108 is holding
SCL or SDA low (clock stretch, bus glitch), the bus remains stuck
after MSSP reset.

**Fix**: After `function_101` returns, disable SSPEN (release pins to
GPIO), bitbang 9 SCL clocks on RB1 (open-drain via TRISB/LATB) while
monitoring SDA on RB0.  If SDA is released after the clocks, generate
a manual STOP (SDA low→high while SCL high).  Re-enable SSPEN.

**Registers**:
- SSPCON1 (0xFC6): SSPEN at bit 5
- TRISB (0xF93): bits 0 (SDA) and 1 (SCL)
- LATB (0xF8A): bits 0 and 1
- PORTB (0xF81): bit 0 (read SDA state)

**Estimated size**: ~24 instructions (48 bytes).

**Placement**: function_072 dead code zone at 0x436C (68 bytes free).

### Fix D: DSP ping after bus-clear

**Problem**: After MSSP reset + bus-clear, the firmware has no way to
verify the TAS3108 is responsive.  If the DSP is in a bad state, all
subsequent I2C writes silently fail.

**Fix**: After bus-clear, attempt a 1-byte I2C random-read from the
TAS3108.  Protocol: START, 0x68 (write addr), register (e.g. 0x00),
RSTART, 0x69 (read addr), read byte, NACK, STOP.  If ACK on
address: bus healthy.  If NACK: retry bus-clear + ping up to 3x.
If persistent NACK: latch DSP fault flag in 0x07F.bit6.

**Pre-requisite**: Identify a safe readable TAS3108 register.  The
TAS3108 datasheet (sleu067a.pdf) register map needs to be checked
for a read-safe register that doesn't change device state.

**Estimated size**: ~30 instructions (60 bytes).

**Placement**: remainder of function_072 dead zone + function_111
dead zone at 0x489A (28 bytes).

### Fix E: DSP fault status reporting

**Problem**: MAIN detects DSP faults (V2.6 ACKSTAT latch, V2.7 ping
failure) but has no way to report them to CONTROL.  CONTROL shows
stale data with no warning.

**Fix**: Add a new status frame in MAIN's status burst (function_050):
BF/08/fault_byte.  The fault_byte encodes:
- bit 0: DSP NACK detected (V2.6 0x07F.bit2 was set)
- bit 1: DSP ping failed (V2.7 0x07F.bit6)
- bit 2: bus-clear attempted (informational)
- bits 3-7: reserved (0)

Sent alongside BF/03, BF/05, BF/07 in each status burst.  Cleared
after CONTROL acknowledges or after successful DSP write.

**Estimated size**: ~12 instructions (24 bytes).

**Placement**: inline in function_050 hook or small stub.

### Fix F: MSSP STOP timeout in function_113

**Problem**: `function_113` (mssp_idle_wait) polls SSPCON2<4:0> and
SSPSTAT.R in an unbounded loop.  V2.5's `function_113_patch` adds a
bounded wait but only for the SSPCON2/SSPSTAT check — the stock PEN
busy-wait inside function_081 at label_572 (0x4510) is NOT wrapped.

**Fix**: Hook the PEN busy-wait at 0x4510 with a bounded version
(reuse `patch_wait_pen_clear_c`).  On timeout: call
`patch_recover_mssp` + bus-clear.

**Estimated size**: ~8 instructions (16 bytes).

**Placement**: inline at 0x4510 (replace 4-byte btfsc/bra loop with
4-byte goto to stub).

---

## V1.63b CONTROL firmware

### Fix E': DSP fault parser

**Problem**: CONTROL's parser does not recognize BF/08.  Unknown
commands are silently dropped.

**Fix**: Add BF/08 handler to the parser dispatch table.  When
received: read fault_byte, store in RAM (e.g. 0x0BC), set a sticky
`dsp_fault` flag in 0x01F.bit7 (or another free bit).

**Estimated size**: ~10 instructions.

### Fix E'': DSP fault UI indicator

**Problem**: CONTROL shows cached volume with no fault indication.

**Fix**: On the Volume screen, when `dsp_fault` is set:
- Display "!" at column 15 (replacing the preset A/B indicator)
- Or blink the volume display
- Or show "DSP ERR" on line 2

When `dsp_fault` clears (MAIN sends BF/08 with fault_byte=0),
restore normal display.

**Estimated size**: ~15 instructions.

### Fix E''': Resync on fault clear

**Problem**: After DSP fault + recovery, CONTROL's display shows
stale settings until the periodic full-sync fires (~20 seconds).

**Fix**: When `dsp_fault` transitions from set to clear (BF/08
fault_byte goes 0→0), reset the full-sync counter (0x09F/0x0A0) to
trigger an immediate full-sync burst on the next display loop
iteration.

**Estimated size**: ~8 instructions.

---

## Tests (must be in place BEFORE implementation)

### Test 1: `test_main_v27_bus_clear_recovers_stuck_slave`

MAIN-side standalone test.  Inject MSSP STOP fault (hold_scl_low
or long stop_busy_cycles), trigger I2C write, verify MAIN detects
the stuck bus, performs bus-clear, and the DSP becomes responsive.

- V2.3/V2.4/V2.5/V2.6: **xfail** (no bus-clear)
- V2.7: **pass**

### Test 2: `test_main_v27_dsp_ping_after_recovery`

MAIN-side standalone test.  Inject address NACKs on dsp34, trigger
volume command, verify MAIN detects NACK (V2.6 latch), then performs
bus-clear + ping.  If ping succeeds (NACKs cleared), DSP is healthy.
If ping fails (NACKs still active), DSP fault flag is latched.

- V2.3/V2.4/V2.5/V2.6: **xfail** (no ping)
- V2.7: **pass**

### Test 3: `test_wire_v27_v163b_dsp_fault_reporting`

Wire-chain e2e test.  V2.7 MAIN + V1.63b CONTROL.  Inject DSP
NACK fault, verify:
1. MAIN sends BF/08 with fault bits set
2. CONTROL's `dsp_fault` flag is set
3. CONTROL shows fault indicator on LCD
4. Clear fault → MAIN sends BF/08 with 0 → CONTROL clears indicator

- V2.6 + V1.62b: **xfail** (no BF/08, no fault UI)
- V2.7 + V1.63b: **pass**

### Test 4: `test_wire_v27_v163b_mssp_stop_cascade_recovery`

Wire-chain e2e test.  Same MSSP STOP fault scenario as
`test_wire_extended_mssp_stop_fault_degrades_dsp_command_path` but
with V2.7 MAIN.  After the fault clears, V2.7's bus-clear + ping
should recover the DSP path.  Volume commands should work after
recovery.

- V2.3/V2.4/V2.5/V2.6: **xfail** (DSP path degraded)
- V2.7 + V1.63b: **pass**

### Test 5: `test_wire_v27_pen_timeout_recovers`

Wire-chain e2e test.  Inject MSSP STOP fault specifically targeting
the PEN busy-wait in function_081 (label_572).  V2.7's PEN timeout
hook should detect the stuck STOP and recover via bus-clear.

- V2.5/V2.6: **xfail** (PEN busy-wait is unbounded)
- V2.7: **pass**

---

## Pre-requisites

### P1: TAS3108 readable register identification

Read `firmware/reference/sleu067a.pdf` (TAS3108 datasheet) and
identify a register that:
- Is readable via I2C random-read protocol
- Does not change device state on read
- Returns a known/predictable value (for ping verification)

Candidate: device ID register, status register, or coefficient
register 0x00 (should return current value).

### P2: gpsim I2C read model verification

Verify that gpsim's I2C regfile module supports I2C random-read
(START, write-addr, reg, RSTART, read-addr, data, NACK, STOP).
The existing I2C regfile module handles writes; read support needs
to be verified or added.

### P3: gpsim MSSP STOP fault model for PEN

Verify that `set_main_mssp_stop_fault(stop_busy_cycles=N)` actually
stalls the PEN phase (SSPCON2.PEN poll).  The current model may
only stall the STOP-condition detection in `function_113`, not the
PEN busy-wait in function_081's label_572.

### P4: Stub space inventory for V2.7

Calculate exact available space after V2.6:
- function_072 dead zone: 0x436C-0x43AF (68 bytes)
- function_111 dead zone: 0x489A-0x48B5 (28 bytes)
- function_113 dead zone: 0x48BA-0x48D3 (26 bytes)
- Any reclaimable space from V2.6 optimizations

Total needed: ~148 bytes (C: 48, D: 60, E: 24, F: 16).
Available: ~122 bytes.  Gap: ~26 bytes.  Need optimization or
additional dead code recovery.

### P5: CONTROL 0x01F bit availability

Verify which bits of CONTROL's 0x01F flags register are free for
the `dsp_fault` flag.  Known usage:
- bit 0: IR_ARMED
- bit 1: CONNECTED/DISPLAY
- bit 2: STANDBY_BUS (driven by wire chain)
- bit 3: cleared at init (V1.62b)
- bit 4: cleared at init (V1.62b)
- bit 5: used in reconnect_wait_done
- bit 6: preset A/B state
- bit 7: free? needs verification

### P6: BF/08 command number availability

Verify cmd=0x08 is not used by any existing MAIN→CONTROL protocol.
Check the command dispatch table in all CONTROL firmware versions.

---

## Implementation order

1. P1-P6 (pre-requisites research)
2. Tests 1-5 (write tests, verify xfail on current versions)
3. V2.7 Fix F (PEN timeout — smallest, independent)
4. V2.7 Fix C (bus-clear)
5. V2.7 Fix D (DSP ping)
6. V2.7 Fix E (fault status frame)
7. V1.63b Fix E' (parser)
8. V1.63b Fix E'' (UI)
9. V1.63b Fix E''' (resync)
10. Full regression: all 33+ tests pass, V2.7+V1.63b zero xfails
