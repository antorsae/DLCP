# Standby Simulation Improvement — Self-Contained Prompt

## Your mission

You are working in `/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis`.
Read `AGENTS.md` for full repo layout and conventions (`CLAUDE.md` is a compatibility mirror).
Python venv: `.venv_ep0/bin/python`.  Run tests with `.venv_ep0/bin/python -m pytest`.

**You have full access to modify the local gpsim fork** at
`vendor/gpsim-0.32.1-xtc/`.  This is a C++ PIC simulator that we
maintain locally.  If a gpsim core limitation blocks your work (e.g. the
EUSART model, oscillator switching, timer behavior, I2C slave model),
you can and should modify the gpsim C++ source directly, rebuild, and
use the updated binary.  See the "gpsim fork" section below for layout
and build instructions.

You must improve the gpsim-based co-simulator so that a **wire-chain
end-to-end test** can reproduce a real field bug: the V1.62b reconnect
wake gate bug documented in `docs/analysis/V162B_RECONNECT_WAKE_BUG.md`.

The final deliverable is a new test in `tests/sim/test_reconnect_wake_gate.py`
(extend the existing file) named `test_v162b_wire_chain_standby_reconnect_dsp_gate`
that:

1. Uses `WireMultiMainChainHarness` (CONTROL + MAIN, real wire UART)
2. Boots to DISPLAY, confirms DSP baseline (volume UP changes dsp34 registers)
3. Triggers a standby cycle (press STBY → Zzz → reconnect → DISPLAY)
4. After reconnect, asserts MAIN's active gate (0x5E.bit3) and DSP behavior
5. **FAILS** when V1.62b is built WITHOUT the `call 0x0C98` fix
6. **PASSES** when V1.62b is built WITH the fix

You should work in a loop: research → implement → test → diagnose → fix → repeat.
It is OK if this takes many iterations.  Commit working milestones along the way.

---

## The two obstacles you must solve

### Obstacle 1: MAIN enters real standby and becomes unreachable

When CONTROL presses STBY, it broadcasts `[B0, 0x03, 0x00]` to all MAINs.
MAIN's parser at `label_155` (0x1C9A) clears the active flag (0x5E.bit3),
then `function_100` dispatches to `function_051` (0x3C0C).

`function_051` does:
```asm
; Three I2C DSP shutdown ops
003c0c:  clrf 0x006           ; function_093(0x1B)
003c10:  call function_093
003c14:  clrf 0x006           ; function_093(0x1C)
003c18:  call function_093
003c1c:  clrf 0x006           ; function_093(0x1D)
003c20:  call function_093

; Baud rate change based on RC2
003c24:  btfss PORTC, RC2     ; test RC2
003c26:  bra   label_485      ; RC2 LOW → label_485
; RC2 HIGH:
003c28:  bsf   LATB, LATB2
003c2c:  movlw 0x3f
003c2e:  movwf SPBRG          ; SPBRG = 0x3F (baud doubled)
003c30:  bsf   OSCCON, SCS1   ; switch oscillator
003c32:  bra   label_486
; RC2 LOW:
003c34:  bcf   LATB, LATB2
003c38:  movlw 0x7f
003c3a:  movwf SPBRG          ; SPBRG = 0x7F (stock baud)
003c3c:  bcf   OSCCON, SCS1   ; no osc switch

; Both paths: disable outputs, Timer0, USB
003c3e:  bcf   LATB, LATB4
003c40-46: bcf  LATA bits 6,3,4,5
...
003c7a:  bcf   T0CON, TMR0ON  ; DISABLE Timer0
003c7c:  bcf   INTCON, T0IE   ; DISABLE Timer0 interrupt
003c7e:  goto  function_116   ; clears UCON (USB), returns
```

After `function_051`: MAIN's oscillator may have switched (if RC2 was
HIGH at entry), Timer0 is off, USB is off.  MAIN stays in the main loop
but with the wrong baud rate and no timer scheduling.  CONTROL's
reconnect polls never get valid responses.  CONTROL stays in Zzz forever.

**On real hardware, the bug manifests when function_051 PARTIALLY FAILS
due to an I2C glitch**.  The active flag is already cleared (in the parser
BEFORE function_051 runs), but function_051's I2C ops timeout, V2.5
recovery fires, and MAIN stays alive with normal baud rate.  You need to
simulate this partial failure.

**Approaches to consider (pick the best one or combine):**

A. **I2C fault injection during standby**: Use `set_main_i2c_fault()` on
   `dsp34` (address NACK, stuck SDA, etc.) to make `function_051`'s three
   `function_093` calls fail.  With V2.5 timeout hooks
   (`enable_main_timeout_test_hooks=True`), the MSSP timeout seed at
   0x04F can be set to 0x00 to trigger timeout.  If the timeout →
   recover → retry → fail → hard-reset path fires, MAIN reboots (bad —
   clears the bug condition).  You need to find a fault mode where V2.5
   recovers successfully on retry (or where the I2C call just returns
   with partial effect) so function_051 continues but the DSP shutdown
   is incomplete.

B. **Breakpoint-based interception**: Set a gpsim breakpoint at the
   `function_051` entry (0x3C0C) or at the baud-rate-change instruction
   (0x3C2E for SPBRG write).  When hit, manually skip the rest of
   function_051 by writing the return address / adjusting PC.  This is
   fragile but deterministic.

C. **RC2 mode override**: `WireMultiMainChainHarness` creates MAINs with
   `rc2_mode="high"`.  If you change it to `rc2_mode="low"`, function_051
   sets SPBRG=0x7F (stock baud, no osc switch).  MAIN's baud rate
   doesn't change, so wire UART still works.  But Timer0 is still
   disabled and function_116 clears USB.  You'd need to verify MAIN can
   still process serial frames without Timer0.

D. **Hybrid approach**: Use rc2_mode="low" to keep baud rate stable,
   AND inject an I2C fault or MSSP timeout to make function_051's DSP
   shutdown writes ineffective (so PBS hardware would stay on in real
   HW).  The remaining question is whether MAIN's main loop runs well
   enough without Timer0 to respond to CONTROL's reconnect polls via
   wire UART.

E. **gpsim register patching mid-flight**: After function_051 completes,
   manually restore SPBRG, OSCCON, T0CON, INTCON to their pre-standby
   values via gpsim register writes.  This simulates "function_051
   failed and V2.5 recovered everything."  Requires knowing when
   function_051 has completed (breakpoint at function_116 return, or
   just after enough steps).

F. **Modify gpsim core to ignore OSCCON.SCS1 writes** (or make them
   configurable).  If gpsim's PIC18F2455 model doesn't actually switch
   the oscillator frequency when SCS1 is set (just records the bit),
   then the baud rate divisor stays at the original Fosc and UART still
   works.  Check `vendor/gpsim-0.32.1-xtc/src/p18x.cc` — if the OSCCON
   `put()` handler doesn't re-derive the clock frequency, this might
   already be the case.  If it DOES switch, you can add a
   `--disable-scs-switch` attribute or simply NOP the clock re-derive.
   This is the cleanest fix because it models the real scenario (MAIN
   stays communicable after partial standby failure) without any
   test-side hacks.

### Obstacle 2: Display loop compensates for missing wake

Even without the fix in `reconnect_wait_done`, CONTROL's display loop
periodically calls `function_028` (full-sync burst, at 0x0B36) which
internally calls `function_034` (standby/wake frame, at 0x0C98).

The full-sync counter (`0x09F`/`0x0A0`) is reset to 0 in
`reconnect_wait_done`.  Full-sync fires when `0x0A0 == 0x4E` (78
iterations of function_035).  Each function_035 call takes roughly one
CONTROL step (~250ms at 1M cycles).  So the full-sync fires ~20 seconds
after reconnect.

**The race window**: on real hardware, the user presses volume/preset
buttons BEFORE the full-sync fires.  Those commands are dropped.  After
the full-sync eventually sends wake, commands would start working again.

**Approaches to make the test catch the bug:**

A. **Timing-sensitive assertion**: Check MAIN's 0x5E.bit3 immediately
   after reconnect (0-2 steps).  Without the fix, the gate is still
   closed.  With the fix, the wake frame arrives in the same step as
   reconnect_wait_done.  Then inject volume commands BEFORE the full-sync
   fires.  This requires the wake frame from `call 0x0C98` to actually
   propagate through the wire chain in 1-2 steps.

   **Subtlety**: function_027 sends the 3 wake bytes via CONTROL's TX ISR.
   They appear in the FileRecorder, get flushed to MAIN's FileStimulus,
   and MAIN's EUSART receives them.  But in the wire chain, MAIN uses
   `transport_mode="native_ring"` — meaning RX is via RAM ring injection,
   NOT via the EUSART FileStimulus.  You may need to verify that MAIN
   actually processes wake bytes delivered through the wire path vs the
   native-ring path, or change the transport mode.

B. **Suppress the full-sync counter**: After reconnect, manually write
   `0x0A0 = 0x00` (or continuously hold it at 0) to prevent the full-sync
   from ever firing.  Then the gate never opens without the fix.
   This is deterministic but invasive.

C. **Use a shorter assertion window**: Don't wait for 78 iterations.
   Check within 1-3 steps of reconnect.  The `call 0x0C98` in
   `reconnect_wait_done` executes in the CONTROL step where reconnect
   succeeds.  The TX ISR sends the bytes during that same step.  The
   bridge flushes them.  MAIN processes them on the next step.  So the
   gate should open 1-2 steps after reconnect with the fix, and stay
   closed without.

---

## Key infrastructure you'll work with

### WireMultiMainChainHarness constructor
```python
WireMultiMainChainHarness(
    control_hex: Path,
    main_hex: Path,
    *,
    main_units: int = 1,          # number of MAINs
    fast_boot: bool = False,
    control_chunk_cycles: int = 1_000_000,  # ~250ms at 4MHz Tcy
    hold_cycles: int = 240_000,
    disable_standby_check: bool = False,    # NOP standby jump in CONTROL
)
```

MAINs are created internally with `rc2_mode="high"`, `standby_mode="hold"`,
`transport_mode="native_ring"`, `bypass_i2c=False`.

### MainChainHarness constructor
```python
MainChainHarness(
    main_hex: Path,
    *,
    chunk_cycles: int = 200_000,
    standby_mode: str = "hold",     # "hold"=0x0230, "release"=0x0220, "keep"=bus
    main_ra0_adc: int | None = None,
    rc2_mode: str = "high",         # "high"/"low"/"keep"
    bypass_i2c: bool = False,
    transport_mode: str = "mailbox", # "mailbox" or "native_ring"
    enable_timeout_test_hooks: bool = False,
)
```

### Key methods
```python
chain.press("STBY")                    # press button on CONTROL
chain.step() -> WireChainStepResult    # step CONTROL + all MAINs
chain.step_many(n)                     # n steps
chain.is_connected() -> bool           # CONTROL 0x01F bit1
chain.is_waiting() -> bool             # LCD contains "WAITING"
chain.lcd_lines() -> (str, str)
chain.run_until_connected(limit=N) -> result | None
chain.run_until_waiting(limit=N) -> result | None
chain.set_link_fault(name, drop=True)  # drop all bytes on a bridge
chain.clear_link_faults()
chain.set_main_i2c_fault("dsp34", main_index=0, address_nack_count=5)
chain.mains[i].read_i2c_regfile("dsp34", addr) -> int  # read DSP register
chain.mains[i]._issue(cmd, timeout)    # raw gpsim command
_read_reg(chain.mains[i]._issue, addr) -> int  # read firmware register
```

### Existing test pattern (from test_main_stdby_pin_io.py)
```python
chain = WireMultiMainChainHarness(ctrl_hex, main_hex, ...)
last = chain.run_until_connected(limit=80)
assert chain.is_connected()
chain.press("STBY")
chain.step_many(40)
assert "ZZZ" in chain.lcd_lines()[0].upper()
# ... check pin states, register values ...
```

### DSP register snapshot (from test_reconnect_wake_gate.py)
```python
def _dsp34_snapshot(main):
    return {r: main.read_i2c_regfile("dsp34", r) for r in range(256)}

def _dsp34_diff(before, after):
    return [(r, before[r], after[r]) for r in range(256) if before[r] != after[r]]
```

### Firmware paths
```python
from dlcp_fw.paths import PATCHED_CONTROL_HEX_V162B, PATCHED_MAIN_HEX
```

### Reverting the fix for XFAIL testing
In `src/dlcp_fw/patch/build_control_presets_ab_v162b.py`, the fix is
one line in `reconnect_wait_done` (around line 299):
```asm
    bsf 0x01F, 1, ACCESS
    call 0x0C98                     ; function_034: wake (bit1=1 -> data=0x01)
    movlw 0x61
```
Remove the `call 0x0C98` line, rebuild with:
```bash
.venv_ep0/bin/python -m dlcp_fw.patch.build_control_presets_ab_v162b
```
Then run your test.  It must FAIL.  Restore the line, rebuild, and it must PASS.

---

## V1.62b reconnect_wait_stub (the CONTROL code under test)

For reference, this is the patched CONTROL assembly at the reconnect path:

```asm
reconnect_wait_stub:
    movlb 0x01
    clrf 0x73, BANKED                ; retry counter

reconnect_wait_loop:
    movlb 0x00
    call 0x0B64                      ; function_029: send poll [B1,04,00]
    movlw 0xC8
    call 0x01BC                      ; function_012: ~200ms delay
    call 0x044A                      ; robust parser wrapper

    ; 4-register handshake: each must differ from 0x80
    movlw 0x80
    subwf 0x0B8, W, BANKED          ; ch1 volume
    skpz
    movlw 0x01
    movwf 0x018, ACCESS

    movlw 0x80
    subwf 0x0B9, W, BANKED          ; ch2 volume
    skpz
    movlw 0x01
    andwf 0x018, F, ACCESS

    movlw 0x80
    subwf 0x0A7, W, BANKED          ; route/status
    skpz
    movlw 0x01
    andwf 0x018, F, ACCESS

    movlw 0x80
    subwf 0x0A1, W, BANKED          ; debounce
    skpz
    movlw 0x01
    andwf 0x018, F, ACCESS

    movf 0x018, F, ACCESS
    bnz reconnect_wait_done          ; all 4 non-0x80 → exit

    ; retry with periodic UART re-prime
    movlb 0x01
    incf 0x73, F, BANKED
    movlw 0x08
    cpfseq 0x73, BANKED
    goto reconnect_wait_loop
    clrf 0x73, BANKED
    movlb 0x00
    call control_uart_soft_recover
    goto reconnect_wait_loop

reconnect_wait_done:
    movlb 0x01
    clrf 0x73, BANKED
    movlb 0x00
    bsf 0x01F, 1, ACCESS            ; enter DISPLAY
    call 0x0C98                      ; function_034: wake (THE FIX)
    movlw 0x61
    movwf 0x09D, BANKED
    movlw 0xEA
    movwf 0x09E, BANKED
    clrf 0x09F, BANKED               ; reset full-sync counter
    clrf 0x0A0, BANKED
    bcf 0x01F, 5, ACCESS
    movlw 0x01
    movwf 0x032, ACCESS
    goto 0x11D8                      ; → label_201 (display loop entry)
```

---

## gpsim fork: layout, key sources, and build

The local gpsim fork lives at `vendor/gpsim-0.32.1-xtc/`.  You own this
code and can modify anything in it.

### Source layout
```
vendor/gpsim-0.32.1-xtc/
├── src/                    # Core simulator
│   ├── gpsim_time.h        # Cycle/time management
│   ├── uart.cc / uart.h    # EUSART model (_TXREG, _RCREG, _RCSTA, baud rate)
│   ├── ssp.cc / ssp.h      # MSSP/I2C master model
│   ├── p18x.cc / p18x.h    # PIC18 processor base (includes OSCCON handling)
│   ├── 14bit-processors.cc # Processor definitions
│   ├── registers.cc / .h   # SFR register framework
│   ├── stimuli.cc / .h     # Pin stimulus (FileStimulus, FileRecorder)
│   ├── modules.h            # Module base class
│   └── ...
├── modules/                # Loadable modules (compiled into libgpsim_modules)
│   ├── i2c-regfile.cc / .h # I2C slave register-file module (our addition)
│   ├── i2c.cc / i2c.h      # I2C master/slave base classes
│   ├── gpsim_modules.cc    # Module registry (construct functions)
│   └── Makefile.am
├── gpsim/                  # CLI entry point
│   └── main.cc
└── regression/             # Built-in regression tests
    └── p18f25k20/
```

### Key C++ classes you may need to modify

- **`_RCSTA`** (`src/uart.cc`): Implements OERR detection, CREN toggle,
  FIFO management.  `_RCREG::push()` calls `_RCSTA::overrun()` when
  `fifo_sp >= 2`.

- **`_TXSTA` / `_TXREG`** (`src/uart.cc`): TRMT flag, baud rate
  generator.  TXREG writes queue bytes for the shift register.

- **`OSCCON`** (`src/p18x.cc` or processor-specific): SCS1 bit controls
  clock source selection.  After function_051 sets SCS1, the effective
  Fosc changes, which affects the UART baud rate divisor.  **gpsim may
  or may not model the oscillator switch correctly** — if it doesn't,
  the baud rate stays at the original value even after SCS1 is set.
  This could be either a problem or an opportunity.

- **`T0CON`** (`src/14bit-tmr.cc` or similar): TMR0ON bit.  When cleared
  by function_051, Timer0 interrupts stop.  The main loop may depend on
  Timer0 for scheduling.

- **`I2CRegFile`** (`modules/i2c-regfile.cc`): The I2C slave module.
  Has fault injection attributes (Address_Nack_Count,
  Address_Stretch_SCL_Cycles, Data_Nack_Count, Data_Stuck_SDA_Cycles,
  Hold_SCL_Low, Stretch_SCL_Cycles).  You can add new attributes or
  behaviors here (e.g. a "fail next N transactions" mode).

### Build commands
```bash
# Full configure (only needed once or after Makefile.am changes)
mkdir -p artifacts/tools/gpsim-xtc/build
cd artifacts/tools/gpsim-xtc/build
env CPPFLAGS=-I/opt/homebrew/include LDFLAGS=-L/opt/homebrew/lib \
  ../../../../vendor/gpsim-0.32.1-xtc/configure --disable-gui
make -C src -j4 libgpsim.la
make -C modules -j4 libgpsim_modules.la
make -C gpsim gpsim

# Incremental rebuild after editing .cc/.h files
cd /Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis
make -C artifacts/tools/gpsim-xtc/build/src -j4 libgpsim.la
make -C artifacts/tools/gpsim-xtc/build/modules -j4 libgpsim_modules.la
make -C artifacts/tools/gpsim-xtc/build/gpsim gpsim
```

The built binary is used via `scripts/gpsim-xtc` (wrapper that sets
library paths).  Verify with: `scripts/gpsim-xtc --version`

### Example: adding a new I2C regfile attribute

If you need a new fault mode (e.g. "fail the next N complete
transactions"), you'd:

1. Add a member to `I2CRegFile` in `modules/i2c-regfile.h`
2. Add an `Integer` attribute subclass in `modules/i2c-regfile.cc`
   (follow the pattern of `I2CRegFileAddressNackCountAttribute`)
3. Register it in the `I2CRegFile` constructor
4. Use it in `match_address()` or `receive_data_byte()` to inject the fault
5. Rebuild modules: `make -C artifacts/tools/gpsim-xtc/build/modules -j4`
6. Expose it in the Python harness via `set_i2c_fault()` in
   `src/dlcp_fw/sim/chain_gpsim.py` (the `MainChainHarness` method)

### Example: modifying OSCCON/SCS behavior

If gpsim's OSCCON model doesn't properly switch the clock source (or if
you want to PREVENT the switch for testing), you can:

1. Find the `OSCCON` register handling in `src/p18x.cc` (or the
   processor-specific file for p18f2455)
2. Modify `put()` to optionally ignore SCS1 writes (controlled by an
   attribute or environment variable)
3. Rebuild core: `make -C artifacts/tools/gpsim-xtc/build/src -j4`

---

## Using codex-cli as a collaborator

You have access to the `mcp__codex-cli__codex` MCP tool.  This launches
a powerful coding agent (OpenAI Codex) that can read the codebase, run
commands, and reason about complex problems.  **Use it as a
sophisticated collaborator when you get stuck.**

### When to call codex-cli

- **After 3 failed experiments**: if you've tried 3 approaches and none
  produced a test that FAILS without fix / PASSES with fix, stop and
  consult codex-cli before trying a 4th.
- **When blocked on gpsim internals**: if you need to understand how
  gpsim models OSCCON, baud rate derivation, Timer0, or clock switching,
  ask codex-cli to read the relevant C++ source and explain the behavior.
- **When you need a fresh perspective**: if your current approach feels
  like it's hitting a wall, ask codex-cli for alternative strategies.

### How to call it

```
mcp__codex-cli__codex(
  prompt="<your question or task>",
  cwd="/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis",
  approval-policy="on-failure",
  sandbox="workspace-write",
)
```

### What to include in your prompt to codex-cli

Write a structured summary:

1. **Goal**: one sentence (e.g. "make MAIN stay UART-reachable after
   function_051 standby in gpsim wire-chain sim")
2. **What I tried**: bullet list of approaches and what happened
3. **Key files**: list the 3-5 most relevant files
4. **Specific question**: what you need codex-cli to investigate or
   suggest (e.g. "Does gpsim's p18f2455 OSCCON model actually re-derive
   the clock frequency when SCS1 is written?  Read src/p18x.cc and
   the processor-specific file to find out.")

### Example codex-cli call

```
mcp__codex-cli__codex(
  prompt="""
Goal: Understand whether gpsim re-derives the UART baud rate when
OSCCON.SCS1 is changed by firmware.

Context: MAIN's function_051 (standby handler) sets OSCCON.SCS1 at
0x3C30 to switch to the secondary oscillator.  On real hardware this
changes Fosc, which changes the baud rate divisor.  In gpsim, we need
to know if this actually affects the simulated baud rate or if it's
a no-op.

Please read these files and trace the code path:
- vendor/gpsim-0.32.1-xtc/src/p18x.cc (search for OSCCON, SCS)
- vendor/gpsim-0.32.1-xtc/src/uart.cc (search for baud, baudrate, spbrg)
- vendor/gpsim-0.32.1-xtc/src/14bit-processors.cc

Tell me: (1) does gpsim model the oscillator switch, (2) does it
affect the UART baud rate, and (3) what's the simplest way to
prevent the baud rate change for test purposes.
""",
  cwd="/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis",
  approval-policy="on-failure",
  sandbox="read-only",
)
```

Use codex-cli liberally.  It's better to ask early and often than to
spend hours going in circles.

---

## Success criteria

Your test must demonstrate this cycle:

```
PASS (with fix):
  boot → DISPLAY → INJECT I2C GLITCH → STBY → Zzz → reconnect → DISPLAY
  → 0x5E.bit3 == 1 (gate open) → volume UP → DSP registers change

FAIL (without fix):
  boot → DISPLAY → INJECT I2C GLITCH → STBY → Zzz → reconnect → DISPLAY
  → 0x5E.bit3 == 0 (gate closed) → volume UP → DSP registers unchanged
```

The I2C glitch is the **initiating fault**.  On real hardware, a transient
I2C bus error between MAIN and the TAS3108 DSP caused function_051's
three `function_093` calls to partially fail.  This meant MAIN stayed
alive (baud rate unchanged, Timer0 still running, main loop still
processing serial frames) but with the active gate already closed by
`label_155`.  Without the glitch, function_051 completes normally and
MAIN enters real standby — which is NOT the bug scenario.

The test must inject the glitch BEFORE pressing STBY so that MAIN's
function_051 fails to fully shut down.  Use the `dsp34` I2C fault
injection (`set_main_i2c_fault`) or MSSP timeout hooks to cause the
I2C portion of function_051 to fail while MAIN remains UART-reachable.

Commit simulator improvements and the test when done.  Update
`docs/analysis/V162B_RECONNECT_WAKE_BUG.md` to remove the "Why no
wire-chain end-to-end" caveat section and document the new test.
