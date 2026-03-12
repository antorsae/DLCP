# Stock DLCP 2.3 / Control 1.4 Sync-Deadlock Analysis

Date: 2026-03-08
Model: Claude Opus 4.6 (high effort, 5 parallel research agents)
Scope: stock MAIN `DLCP Firmware V2.3.hex` and stock CONTROL `DLCP Control Firmware V1.4.hex`
Reference: PIC18F2455/2550 datasheet `firmware/reference/39632e.pdf` with repo companion `firmware/reference/39632e.md`

## Executive Summary

The stock firmware contains **20 concrete bugs** across both MCUs (9 in MAIN, 11 in CONTROL) that collectively explain the observed random hangs, lost sync, and permanent "WAITING FOR DLCP" states. The failures result from a cascade of architectural deficiencies:

1. **No watchdog timer** on either MCU -- zero automatic recovery from any hang.
2. **Unbounded busy-wait loops** -- 11 I2C locations in MAIN, plus UART TX on both units.
3. **Serial frame desynchronization** -- OERR recovery resets frame state without draining FIFO.
4. **IR decode blocks ISR for ~10ms** -- guarantees serial overrun on every remote button press.
5. **Infinite wait loops with no timeout** -- both boot and reconnect paths on CONTROL.
6. **Fire-and-forget protocol** -- no ACKs, no sequence numbers, no frame markers, no checksums.

These are sufficient to produce exactly the failure patterns reported:

- MAIN stops acting on volume/mute/input commands (I2C deadlock or frame desync).
- CONTROL falls to "WAITING FOR DLCP" and never recovers (infinite wait, no timeout).
- In multi-unit chains, one stuck MAIN wedges the entire bus.
- Only a power cycle recovers either unit.

## Safety Net Analysis: WDT and Reset Configuration

### PIC18F2455/2550 Watchdog Capabilities (from 39632e.pdf / 39632e.md)

The WDT uses the INTRC oscillator with a base period of 4ms, multiplied by a 16-bit postscaler (WDTPS3:WDTPS0). Available timeouts range from 4ms (1:1) to 131s (1:32768). Two control levels exist:

- **WDTEN** (CONFIG2H bit 0): Hardware fuse. When 1, WDT is always on (software cannot disable).
- **SWDTEN** (WDTCON bit 0): Software enable. Only effective when WDTEN=0.

On timeout: full device reset if running, wake-up if in SLEEP.

### Stock Configuration -- Both MCUs

| Config Bit | Main v2.3 | Control v1.4 | Impact |
|------------|-----------|--------------|--------|
| **WDTEN** | **0 (OFF)** | **0 (OFF)** | No watchdog recovery |
| **WDTPS** | 1:32768 (irrelevant) | -- | WDT disabled regardless |
| **STVREN** | **0 (OFF)** | **0 (OFF)** | Stack overflow = silent corruption, not reset |
| **BOR** | Enabled, 2.0V min | Enabled, 2.0V min | Only extreme brownout triggers reset |
| **WDTCON writes** | None | None | WDT never enabled at runtime either |
| **CLRWDT in code** | 1 vestigial (0x4962) | **Zero** | Confirms WDT was never intended to run |

**Conclusion:** There is absolutely no automatic recovery mechanism. Every busy-wait deadlock, every I2C bus lockup, every protocol desync that causes an infinite poll loop -- all are permanent until power cycle.

## Main Unit v2.3 -- Bug Catalog (9 Bugs)

### BUG M1 [CRITICAL]: I2C/DSP Busy-Wait Loops -- No Timeout

**11 locations** where the firmware polls SSPCON2 or SSPSTAT in a tight loop waiting for the I2C/MSSP engine, with no timeout, no CLRWDT, and no fallback:

| Address | Function | Condition Polled | Context |
|---------|----------|-----------------|---------|
| `0x4246` | function_072 | `SSPCON2.SEN` (Start) | Generic I2C start |
| `0x4258` | function_072 | `SSPCON2.RSEN` (Repeated Start) | Generic I2C restart |
| `0x426C` | function_072 | `SSPCON2.ACKEN` (ACK) | Generic I2C ACK |
| `0x4272` | function_072 | `SSPCON2.PEN` (Stop) | Generic I2C stop |
| `0x44EA` | (DSP init) | `SSPCON2.SEN` (Start) | TAS3108 initialization |
| `0x3870` | (DSP write) | `SSPCON2.SEN` (Start) | TAS3108 coefficient write |
| `0x389C` | (DSP write) | `SSPCON2.PEN` (Stop) | TAS3108 coefficient write |
| `0x46C0` | function_093 | `SSPCON2.SEN` (Start) | EEPROM access |
| `0x3E92` | function_056 | `PIR1.SSPIF` | SPI/I2C completion flag |
| `0x3EB8` | function_056 | `SSPSTAT.BF` | Buffer Full flag |
| `0x466A` | function_093 | `SSPSTAT.BF` | I2C receive buffer |

Additionally, `function_113` at `0x48B6` combines multiple SSPCON2/SSPSTAT checks into a compound busy-wait:

```asm
0048b6:  movff  SSPCON2, temp
0048ba:  movlw  0x1f
0048bc:  andwf  temp, F          ; mask lower 5 bits of SSPCON2
0048be:  btfsc  STATUS, Z        ; if all five control bits clear...
0048c0:  btfsc  SSPSTAT, R       ; ...and R/W bit still set
0048c2:  bra    function_113     ; loop forever
```

**Root cause of main unit deadlocks:** I2C bus lockup (SDA/SCL stuck low) is a well-documented failure mode. Common triggers include ESD events on the I2C lines, DSP not ready during power sequencing, or bus contention. When it occurs, the PIC hangs forever in one of these 11+ loops. With WDT disabled, only a power cycle recovers.

**Severity:** CRITICAL -- most probable cause of observed "main unit stops responding to commands."

### BUG M2 [HIGH]: UART TX Busy-Wait -- No Timeout

**Address:** `0x489A` (label_605, function_111)

```asm
00489a:  btfss  TXSTA, TRMT      ; TX shift register empty?
00489c:  bra    label_605        ; loop forever
00489e:  movff  temp, TXREG      ; send byte
```

Every serial byte transmitted by the main unit passes through this unbounded loop. If TRMT never asserts -- possible during a race between standby transition code at `0x3C2A` (which changes SPBRG without waiting for TX completion or disabling TXEN) and a pending TX operation -- the firmware hangs permanently.

**Severity:** HIGH -- called dozens of times per main-loop iteration during active serial communication.

### BUG M3 [HIGH]: EEPROM Write Disables ALL Interrupts for ~4ms

**Address:** `0x43EA`-`0x43F6` (function_075/label_552)

```asm
0043ea:  btfsc  INTCON, GIE      ; save GIE state
0043ec:  movlw  0x01
0043ee:  movwf  temp
0043f0:  bcf    INTCON, GIE      ; DISABLE ALL INTERRUPTS
0043f2:  rcall  function_076     ; trigger EEPROM write
0043f4:  btfsc  EECON1, WR       ; write complete?
0043f6:  bra    label_552        ; busy-wait ~4ms, GIE=0
```

PIC18 EEPROM write takes ~4ms. During this entire period, GIE is cleared. At 31,250 baud (320us/byte), approximately **12 serial bytes** (4 complete 3-byte frames) arrive during a single EEPROM write. The USART has only a 2-deep hardware FIFO, so OERR (overrun error) is **guaranteed**.

**Note:** The GIE disable is technically only required for the 5-instruction EEPROM unlock sequence (`0x55`/`0xAA`/`WR=1`), not the entire 4ms write cycle. This is an implementation error that causes unnecessary serial data loss.

**Severity:** HIGH -- every EEPROM write guarantees serial frame loss.

### BUG M4 [HIGH]: OERR Recovery Resets Frame State Machine -- Permanent Desync

**Address:** `0x3B7C`-`0x3B8A` (ISR OERR handler)

```asm
003b7c:  btfss  RCSTA, OERR      ; overrun error?
003b7e:  bra    label_484        ; no error -> exit
003b80:  bcf    RCSTA, CREN      ; clear CREN to reset OERR
003b82:  nop
003b84:  bsf    RCSTA, CREN      ; re-enable continuous receive
003b86:  bsf    0x5e, 0          ; set error flag
003b88:  movlb  0x0
003b8a:  clrf   0x98, B          ; RESET frame counter to 0
```

When OERR triggers (guaranteed by M3 during EEPROM writes), the ISR:

1. Toggles CREN to clear the error -- but **does not read RCREG** to drain the 2-byte FIFO first (2 bytes are lost).
2. Resets the frame position counter (`0x098`) to zero -- the next byte received is treated as byte 1 (route byte) regardless of its actual position in the 3-byte frame.

Since the protocol uses no start-of-frame marker (route bytes are ordinary values like `0xB0`/`0xBF`), a data byte with bit 7 set will be misinterpreted as a route byte, causing **permanent protocol desynchronization** until the frame boundary accidentally realigns.

**The M3->M4 chain** (EEPROM write -> OERR -> frame reset) is the strongest candidate for "commands stop working" -- the main unit receives serial data but parses it at the wrong frame offset, silently discarding valid commands.

**Severity:** HIGH -- directly causes sync loss between control and main units.

### BUG M5 [MEDIUM-HIGH]: Timer3 Blocking Delays -- Up to 1500ms

**Address:** `0x449E` (label_569, function_079)

```asm
00449e:  btfss  PIR2, TMR3IF     ; Timer3 overflow?
0044a0:  bra    label_569        ; tight busy-wait
```

This general-purpose delay function blocks the main loop entirely. It is called during:

- Power-up initialization: **1500ms** delay at `0x2DFC` (GIE=0 at this point)
- Standby transitions: 250ms at `0x3C6C`
- ADC polling: 10ms at `0x2D9E`
- Serial inter-byte timing: 1-2ms

During blocking delays, the 192-byte RX circular buffer (64 frames max) can overflow. At maximum serial throughput, the buffer fills in ~20ms.

**Severity:** MEDIUM-HIGH -- causes RX buffer overflow during long delays, especially at boot.

### BUG M6 [MEDIUM]: RX Circular Buffer -- No Overflow Detection

**Address:** `0x3B60`-`0x3B7A` (ISR RX handler)

The ISR stores received bytes at `0x200 + write_idx` and wraps `write_idx` at 192 (`0xBF`), but **never compares write_idx against read_idx**. If the main loop falls behind in consuming serial data, the write pointer silently overwrites unread data. The consumer at `function_087` (`0x45FA`) only checks `write_idx != read_idx` for empty detection -- there is no full/overflow state.

**Severity:** MEDIUM -- silent data corruption rather than deadlock, but leads to unpredictable command behavior.

### BUG M7 [MEDIUM]: Flash Write Returns with GIE=0

**Address:** `0x42B8`-`0x42F2` (function_069)

```asm
0042b8:  bcf    INTCON, GIE      ; disable interrupts
         ; ... flash erase + write sequence #1 ...
0042d2:  btfsc  EECON1, WR       ; busy-wait for write #1
0042d4:  bra    label_546
         ; ... flash write sequence #2 ...
0042ec:  btfsc  EECON1, WR       ; busy-wait for write #2
0042ee:  bra    label_547
0042f0:  bcf    EECON1, WREN
0042f2:  return                  ; RETURNS WITH GIE STILL CLEARED
```

GIE is cleared at entry and **never restored** before return. All interrupt processing (serial RX/TX, USB, timers) stops until GIE is eventually re-enabled much later at `0x3954` in function_045. Serial data arriving during this window is permanently lost.

**Severity:** MEDIUM -- only during cold boot config writes, but guarantees interrupt loss for a significant window.

### BUG M8 [MEDIUM]: No CLRWDT in Main Loop

The only CLRWDT in executable code is at `0x4962` (function_127), called only from USB disconnect/suspend handling. The main processing loop at `0x48CA` (label_607: `call function_026` / `call function_102` / `bra label_607`) contains **no CLRWDT**. This confirms WDT was never designed to be active -- if enabled, the main loop would constantly reset.

**Severity:** MEDIUM -- confirms no safety net exists by design.

### BUG M9 [MEDIUM]: Power-Up ADC Loop Can Stall Indefinitely

**Address:** `0x2D96`-`0x2DC6` (label_341 in function_024)

```asm
002d8c:  bcf    INTCON, GIE      ; interrupts OFF for entire boot sequence
002d96:  bsf    ADCON0, GO       ; start ADC conversion
         ; ... 10ms delay via function_079 ...
002da2:  btfsc  ADCON0, GO       ; ADC done?
         ; ... read result ...
002dc4:  bnc    label_341        ; if result < 0x0236 -> loop forever
```

The boot sequence polls RA0/AN0 (power supply voltage) with GIE=0. If voltage never exceeds threshold `0x0236` (566 / 1024 * Vref), this loop runs forever. This is a power-good check with no timeout -- on marginal power supply or hardware fault, the unit hangs silently with no LCD output, no serial, no diagnostics.

**Severity:** MEDIUM -- only affects boot with abnormal power conditions.

## Control Unit v1.4 -- Bug Catalog (11 Bugs)

### BUG C1 [CRITICAL]: Boot Handshake Infinite Wait -- "WAITING FOR DLCP"

**Address:** `0x11DE` (label_204)

```
label_204:
  call function_029           ; send poll: B1 04 00
  call function_012           ; short delay (~200 cycles)
  call function_019           ; process RX buffer
  ; Check ALL FOUR sentinel registers:
  ;   0xB8, 0xB9, 0xA7, 0xA1 must ALL differ from 0x80
  movlw 0x80
  subwf 0xb8, W               ; channel 1 volume
  ; ... AND with 0xB9, 0xA7, 0xA1 checks ...
  skpnz
  bra   label_204             ; ALL FOUR must change -> loop forever if any stuck
```

After displaying "Firmware V1.4" and "Waiting for DLCP" on the LCD (at `0x11C6`), the control unit sends status poll frames and waits for ALL FOUR parameter registers to change from their default value of `0x80`.

**Exit condition:** `(0xB8 != 0x80) AND (0xB9 != 0x80) AND (0xA7 != 0x80) AND (0xA1 != 0x80)`

If the main unit never responds, or responds but sends `0x80` for any ONE of these parameters, or if the response frames are lost/corrupted due to any of the M-series bugs, **the control unit stays in this loop forever**.

There is no timeout, no retry budget, no UART reset, no fail-open path.

**Severity:** CRITICAL -- this is the primary reported hang.

### BUG C2 [CRITICAL]: Reconnection Infinite Wait -- "WAITING FOR DLCP"

**Address:** `0x130A` (label_216)

Reached after the "Zzz..." standby state when the user presses a button:

```
  bcf    flags, 1              ; clear connected flag
  ; Display "Waiting for DLCP" on LCD (0x12F4)
label_216:
  call   function_029          ; send poll: B1 04 00
  call   function_012          ; short delay
  call   function_019          ; process RX buffer
  btfss  flags, 1              ; connected flag set?
  bra    label_216             ; NO -> loop forever
```

Identical structure to C1. The connected flag (`0x1F.bit1`) is only set by incoming `cmd=0x03, data=0x01` frames from the main unit. If the main unit is hung (BUG M1) or if response frames are being dropped/corrupted (BUGs M3+M4), this loop runs forever.

**Severity:** CRITICAL -- this is the reconnection hang path.

### BUG C3 [HIGH]: IR Decode in ISR Blocks Serial for ~10ms

**Address:** `0x042A` (ISR calls function_017 at `0x021E`)

The ISR's RBIF (port-B change interrupt) handler directly calls function_017, the IR remote decoder. This function bit-bangs RC-5 protocol timing using busy-wait loops:

- ~880 cycles per bit sample delay
- 32 bits total
- **Total blocking time: ~28,160 cycles = ~9.4ms at 12MHz Fosc**

During this ~10ms window inside the ISR:
- No serial TX interrupts fire (TX buffer stalls)
- No serial RX interrupts fire
- At 31,250 baud (320us/byte), **~29 bytes arrive** but only 2 fit in the USART FIFO
- **OERR is guaranteed** on every IR button press during active serial communication

**Trigger scenario:** User presses IR remote while main unit is sending status responses. Overrun occurs, triggering C4+C5, causing frame desync. If this happens during the C2 reconnection loop, the control unit may never see a valid `cmd=0x03` response and stays stuck forever.

**Note:** During the C1 boot loop at label_204, RBIE is not enabled (`0x10A0`), so IR does not interfere with boot. But during C2 reconnection, function_042 at `0x0D24` enables RBIE, making IR reception directly problematic.

**Severity:** HIGH -- every IR press during reconnection can permanently break the serial parser.

### BUG C4 [HIGH]: OERR Recovery Doesn't Drain FIFO

**Address:** `0x044A` (function_019, OERR handler)

```asm
  btfss  RCSTA, OERR          ; overrun error?
  goto   label_038
  bcf    RCSTA, CREN          ; clear CREN to reset OERR
  nop
  bsf    RCSTA, CREN          ; re-enable
```

Standard PIC18 OERR recovery requires reading RCREG twice to drain the 2-byte FIFO **before** toggling CREN. This firmware skips that step. The 2 FIFO bytes are silently lost, which can desynchronize the 3-byte frame protocol if the lost bytes include a frame boundary.

**Severity:** HIGH -- directly contributes to frame desynchronization.

### BUG C5 [HIGH]: No Frame Resynchronization Mechanism

**Address:** `0x0478`-`0x0606` (frame parsing state machine in function_019)

The frame parser uses counter `0xA6` to track position within a 3-byte frame (route/cmd/data). When a byte is lost (via C3/C4), the counter stays at an intermediate value, and the next byte is parsed at the wrong position.

The only partial protection is a `>= 0x80` check on potential route bytes:

```asm
  movlw  0x80
  subwf  0xb6, W              ; is received byte >= 0x80?
  skpc
  goto   label_046            ; no -> treat as cmd/data
  ; yes -> treat as route byte
```

This helps if route bytes always have bit 7 set and data bytes don't, but command bytes can have high values, and there is **no timeout on partial frames** -- if byte 1 arrives but byte 2 never comes, the parser waits indefinitely for the next byte to arrive and treats it as byte 2 regardless of what frame it actually belongs to.

**Severity:** HIGH -- once desynchronized, the parser may never realign.

### BUG C6 [HIGH]: TX Buffer Full Busy-Wait

**Address:** `0x0628` (label_068, function_020)

```asm
label_068:
  movf   new_write_ptr, W
  subwf  0x96, W              ; compare with read pointer
  skpnz
  bra    label_068            ; BUSY WAIT if buffer full
```

When the 48-byte TX circular buffer is full, mainline code busy-waits until the ISR drains at least one byte. If interrupts are disabled or TX interrupt processing fails for any reason, this loop is permanent.

**Severity:** HIGH (latent -- unlikely under normal operation but no timeout).

### BUG C7 [HIGH]: Periodic Full-Sync Burst Creates Heavy Bus Load

**Address:** `0x0B52` (function_028)

The periodic full-sync sender emits per cycle:

- 6 channel configuration frames (`cmd 0x17`-`0x1C`)
- Link-address frame (`cmd 0x1E`)
- Volume frame (`cmd 0x07`)
- Input frame (`cmd 0x06`)
- Mute frame (`cmd 0x03`)
- Timeout frame (`cmd 0x1D`)
- Standby frame

Total: **~47 three-byte frames** per sync cycle with minimal inter-frame delays. On the 31,250 baud bus (960us per frame), this burst takes ~45ms and saturates the link. function_042 at `0x0D24` can trigger this even during reconnect behavior.

On the receiving end, MAIN's 192-byte buffer (64 frames) can be overwhelmed if multiple bursts arrive during I2C or EEPROM blocking operations, causing the M4-M6 overflow/desync cascade.

**Severity:** HIGH -- increases pressure on all transport bugs.

### BUG C8 [MEDIUM]: Standby State Machine Can Oscillate

**Address:** `0x129E` (label_214, "Zzz..." state) to `0x130A` (label_216, reconnect)

The state machine path is:

```
DISPLAY (0x1226) -> check flags.1
  if clear -> STANDBY (0x129E): display "Zzz..."
    -> wait for button press
    -> RECONNECT (0x130A): display "Waiting for DLCP"
      -> poll forever for flags.1
      -> if set -> DISPLAY
```

The `flags.1` (connected) bit can be cleared by both:
1. Parser receiving `cmd=0x03, data=0x00` (explicit disconnect)
2. Local reconnect/timeout logic (idle counter expiry)

If the idle counter expires frequently (e.g., because responses are being lost due to M3/M4 or C3/C4), the control unit cycles through DISPLAY -> STANDBY -> RECONNECT repeatedly. Each transition redisplays LCD strings and re-enters the infinite poll loop. This creates the "flapping" behavior observed in simulation traces.

**Severity:** MEDIUM -- contributes to user-visible instability.

### BUG C9 [LOW]: EEPROM Write Blocking (Non-Critical)

**Address:** `0x01B2` (label_013, function_011)

EEPROM writes busy-wait ~4ms each, and function_025 can write ~50 bytes during preset save (~200ms total). However, GIE remains enabled during control EEPROM writes, so the ISR continues handling serial RX/TX. This is less severe than the MAIN version (M3) but still blocks mainline processing.

**Severity:** LOW -- ISR keeps serial alive.

### BUG C10 [LOW]: LCD Write Uses Fixed Delays, Not Busy Flag

**Address:** `0x00EC` (function_005)

LCD character writes use ~50us fixed delays rather than polling the LCD busy flag. Full screen refresh (~1.6ms for 2x16 characters) is wasted CPU time. Not normally a problem, but combined with multiple LCD updates during boot sequence, accumulated delays create windows for serial timing issues.

**Severity:** LOW.

### BUG C11 [INFO]: Intentional Hard-Halt Trap at Low-Priority Vector

**Address:** `0x0020` (label_003)

```asm
label_003:
  bra    label_003            ; infinite loop -- intentional trap
```

Located at the low-priority interrupt vector (`0x0018`). Since firmware uses single-priority mode (IPEN=0), this should never be reached via a real interrupt. However, stack corruption or a wild jump could land here, creating an unrecoverable hang (no WDT recovery). This appears to be a debug trap.

**Severity:** INFO (intentional, but relevant given no WDT).

## Protocol Design Flaws

The 31,250 baud current-loop serial protocol has fundamental architectural weaknesses that amplify all firmware bugs:

| Design Issue | Impact |
|-------------|--------|
| **No acknowledgment** | Sent frames are never confirmed received; lost frames are never retransmitted |
| **No sequence numbers** | No mechanism to detect missing or out-of-order frames |
| **No start-of-frame marker** | Cannot resynchronize after byte loss (route byte 0xB0 is indistinguishable from a data byte by value) |
| **No checksums or CRC** | Corrupted bytes are accepted silently; bit errors cause wrong commands |
| **No heartbeat with bounded timeout** | Control detects main death only via idle counter expiry, which takes an arbitrary time |
| **No flow control** | Sender has no backpressure mechanism; burst traffic overwhelms receiver buffers |
| **Fire-and-forget commands** | State divergence between control and main is permanent until power cycle |
| **Broadcast only (0xB0)** | No per-unit addressing for commands; if one unit in a chain misses a frame, it diverges with no correction mechanism |

## The Deadlock Chains

### Chain 1: I2C Bus Lockup (Most Probable Main Hang)

```
DSP glitch / ESD event / power sequencing race
  -> I2C SDA or SCL stuck LOW
  -> MAIN enters one of 11 I2C busy-wait loops (BUG M1)
  -> MAIN hangs permanently (no WDT, no timeout)
  -> MAIN stops responding to serial poll frames
  -> CONTROL idle counter expires
  -> flags.1 cleared -> "Zzz..." standby
  -> User presses button
  -> CONTROL enters label_216 "Waiting for DLCP" (BUG C2)
  -> Polls forever -> BOTH UNITS PERMANENTLY HUNG
```

### Chain 2: EEPROM/OERR Desync Cascade (Most Probable Sync Loss)

```
User changes preset or parameter -> EEPROM write triggered on MAIN
  -> GIE=0 for ~4ms (BUG M3)
  -> USART FIFO overflows -> OERR set
  -> ISR OERR handler resets frame counter to 0 (BUG M4)
  -> Next bytes parsed at wrong frame offset
  -> MAIN misinterprets commands (volume byte as route, command as data)
  -> MAIN executes wrong operations or ignores valid commands
  -> User sees "volume doesn't change" / "mute doesn't work"
  -> State diverges permanently (no protocol recovery mechanism)
```

### Chain 3: IR Remote Desync (Reconnection Failure)

```
MAIN hangs or resets (any cause)
  -> CONTROL detects loss of connection, enters "Zzz..." standby
  -> User presses IR remote to wake
  -> CONTROL enters reconnection loop label_216 (BUG C2)
  -> MAIN starts responding with status frames
  -> User presses another IR button while status frames arrive
  -> IR decode in ISR blocks serial RX for ~10ms (BUG C3)
  -> OERR guaranteed (~29 bytes arrive, FIFO holds 2)
  -> OERR recovery doesn't drain FIFO (BUG C4)
  -> Frame parser desynchronized (BUG C5)
  -> CONTROL never sees valid cmd=0x03 response
  -> flags.1 never set -> "Waiting for DLCP" forever
```

### Chain 4: Full-Sync Burst Saturation

```
CONTROL sends periodic full-sync burst (BUG C7)
  -> ~47 frames (~45ms) hit MAIN's 192-byte RX buffer
  -> MAIN is mid-I2C DSP write (blocking, BUG M1)
  -> RX buffer wraps, overwrites unread frames (BUG M6)
  -> MAIN misses critical command frames
  -> Next sync burst arrives before previous one is processed
  -> In multi-unit chain: frames forwarded through stuck unit never reach downstream
  -> Downstream units fall out of sync permanently
```

## Simulator Validation Notes

### What the simulator confirms

- Stock CONTROL naturally parks at "Waiting for DLCP" without a cooperating MAIN (confirmed via `gpsim_lcd_capture_decode.py` with 50M cycles).
- Boot sequence: "Firmware V1.4" -> "Waiting for DLCP" -> "Volume: / -96.0dB" (only with synthetic heartbeat injection).
- Headless chain diagnostics show `overrun_total = 348` in single-main 8-second runs, confirming buffer pressure.
- The simulation required three fixes to reach stable DISPLAY mode: dead stimuli fix, heartbeat model, and transport model corrections.

### What the simulator cannot reproduce

- **I2C bus lockup:** The TAS3108 DSP is not modeled. I2C transactions are instantaneous in the simulator.
- **Real UART ISR timing:** The gpsim harness injects bytes directly into RAM ring buffers, bypassing the physical USART and ISR entirely.
- **Concurrent execution:** Control and main simulations run sequentially. Real hardware runs both PICs simultaneously with potential timing races.
- **IR interference:** IR decode timing collisions with serial reception are not modeled.
- **EEPROM write timing:** Instantaneous in the simulator vs. ~4ms on real hardware.
- **Clock drift:** Both units use the same cycle counter; real hardware has separate oscillators that drift.

### Simulator-identified issues (previously fixed in harness)

1. gpsim `period 0` created dead stimuli -> phantom button presses -> state machine cycling
2. Missing heartbeat model -> function_042 deadlock (bit3 never set)
3. LinkPipe credit banking -> unrealistic mailbox saturation (mean occupancy ~23/30, 214/289 frames dropped)

## Relation to Later Stock Control Versions

| Feature | V1.4 | V1.5b | V1.6b |
|---------|------|-------|-------|
| Boot infinite wait | Yes | Yes | Yes |
| Reconnect infinite wait | Yes | Yes | Yes |
| IR decode in ISR | Yes | Yes | Yes |
| OERR FIFO drain bug | Yes | Yes | Yes |
| Frame resync mechanism | None | None | None |
| WDT enabled | No | No | No |
| Periodic sync burst size | ~47 frames | ~47 frames | **Reduced** |
| cmd=0x18 bootloader entry | Yes | **Removed** | **Removed** |
| CONFIG1L (USB bootloader) | 0x00 (works) | 0xFF (**broken**) | 0xFF (**broken**) |

Later versions do not fix any of the deadlock/desync bugs. V1.6b reduces periodic sync load (which helps with buffer pressure) but retains all fundamental flaws. None add timeouts, WDT, or frame resynchronization.

## Recommended Fix Order

### Phase 1: Immediate Reliability (Prevent Permanent Hangs)

1. **Add bounded timeout to CONTROL wait loops** at `0x11DE` and `0x130A`. After N seconds without response, reset UART state, clear frame counter, and retry. This alone transforms permanent hangs into temporary ones.

2. **Add timeout + recovery to MAIN I2C busy-waits** (all 11 locations). On timeout: reset MSSP module (clear SEN/PEN/RSEN/ACKEN, toggle SSPEN), set error flag, return failure to caller.

3. **Enable WDT** on both MCUs. CONFIG2H WDTEN=1, WDTPS=1:512 (~2 second timeout). Add `CLRWDT` in main processing loops. This provides automatic recovery from any remaining unhandled hang.

### Phase 2: Fix Serial Reliability (Prevent Sync Loss)

4. **Fix OERR recovery on both units** (M4, C4). Read RCREG twice before toggling CREN to drain the FIFO.

5. **Keep GIE=1 during EEPROM write busy-wait** (M3). Only disable interrupts for the 5-instruction unlock sequence, not the entire 4ms write.

6. **Move IR decode out of ISR** (C3). Use Timer capture for edge timing or at minimum disable RCIE during IR decode and drain RCREG after.

7. **Add frame sync timeout** (C5, M4). If a partial frame (1 or 2 bytes received) is not completed within ~10ms, reset the frame counter to 0 and discard the partial frame.

### Phase 3: Protocol Hardening (Prevent State Divergence)

8. **Add RX buffer overflow detection** (M6, C-series). When write pointer would overwrite read pointer, either advance read pointer (discard oldest) or set a buffer-full flag.

9. **Reduce periodic sync burst** (C7). Gate full-sync to only send changed parameters, or add inter-frame pacing.

10. **Add UART TX timeout** (M2). After ~10ms without TRMT, reset UART and report error.

## Concrete Patch Targets

### CONTROL

| Address | Bug | Fix |
|---------|-----|-----|
| `0x11DE` | C1: boot wait | Add iteration counter, timeout after ~5s, reset UART + retry |
| `0x130A` | C2: reconnect wait | Same as above |
| `0x042A` | C3: IR in ISR | Disable RCIE before IR decode, drain RCREG after, or move to timer |
| `0x044A` | C4: OERR no drain | Add two RCREG reads before CREN toggle |
| `0x0478` | C5: no frame resync | Add Timer-based timeout on partial frames |
| `0x0628` | C6: TX full wait | Add timeout counter |
| `0x0B52` | C7: sync burst | Reduce frame count or add pacing |

### MAIN

| Address | Bug | Fix |
|---------|-----|-----|
| `0x4246`-`0x46C0` | M1: I2C waits (11 sites) | Add timeout counter, MSSP reset on timeout |
| `0x489A` | M2: TX wait | Add timeout, UART reset on timeout |
| `0x43F0` | M3: EEPROM GIE=0 | Move GIE=0 to only cover unlock sequence |
| `0x3B7C` | M4: OERR frame reset | Add two RCREG reads, preserve frame counter |
| `0x449E` | M5: Timer3 delay | Add CLRWDT, consider non-blocking approach |
| `0x3B60` | M6: RX overflow | Add write_idx vs read_idx check |
| `0x42B8` | M7: GIE not restored | Add `bsf INTCON, GIE` before return |

### CONFIG

| Register | Current | Recommended |
|----------|---------|-------------|
| CONFIG2H WDTEN | 0 (OFF) | 1 (ON) |
| CONFIG2H WDTPS | 1:32768 | 1:512 (~2s timeout) |
| CONFIG4L STVREN | 0 (OFF) | 1 (ON, reset on stack overflow) |

## Bottom Line

The stock firmware is not merely "lacking robustness" -- it contains **specific, identifiable bugs** that create deterministic deadlock paths. The combination of:

- Unbounded busy-waits (I2C, UART TX, EEPROM)
- Serial frame desynchronization (OERR handler resets state, doesn't drain FIFO)
- Interrupt-blocking operations (EEPROM writes, IR decode in ISR)
- Infinite wait loops with no timeout (boot and reconnect)
- Zero recovery mechanisms (no WDT, no stack overflow reset)
- A fragile fire-and-forget protocol (no ACKs, no checksums, no frame markers)

...makes periodic hangs **inevitable** in real-world operation, not just possible. The only question is how long between occurrences, which depends on environmental factors (ESD susceptibility, power supply quality, IR remote usage patterns, EEPROM write frequency).

The highest-confidence root causes for the specific symptoms reported are:

1. **"Main unit ignores commands"** -> I2C bus lockup (M1) or OERR frame desync (M3+M4)
2. **"WAITING FOR DLCP" stuck** -> Infinite wait loops (C1/C2) triggered by main not responding
3. **"Control hangs when main hangs"** -> No timeout in poll loops + no WDT = both units dead

All of these are fixable via binary patches to the existing firmware images.
