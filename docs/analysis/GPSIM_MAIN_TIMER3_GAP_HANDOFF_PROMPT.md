# gpsim MAIN Timer3 Gap — Handoff Prompt

Date: 2026-03-12

> Historical note (updated 2026-03-12): the failing `test_main_gpsim_timer3_compare.py`
> path was caused by the repo's old harness-side Timer3 emulation strategy timing out
> on repeated CLI breakpoints. The local `gpsim-xtc` fork does raise native
> `PIR2.TMR3IF` on the stock MAIN `function_079` path. Current compare/native-ring
> runs should treat this prompt as archival context, not the live status.

Use this as the direct prompt for another Codex instance.

```text
You are working in:
/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis

Goal:
Close the remaining MAIN-side gpsim gap that blocks reliable CONTROL<->MAIN native-ring / reconnect simulation. The current blocker is Timer3-related behavior on the MAIN PIC18F2455 path, not the CONTROL PIC18F25K20 model.

Primary requirement:
Base the implementation on authoritative Microchip documentation. Treat firmware/reference/39632e.pdf as ground truth. Use firmware/reference/39632e.md for line-stable local citations. If the Markdown conversion has a malformed or blank table row, follow the PDF, not the Markdown. Do not use the removed legacy text conversion as a source.

Current observed problem:
In the native-ring MAIN simulation path, stock MAIN and V2.5 can stall in the Timer3 wait loop at function_079:
- firmware/disasm/main/gpdasm_output.asm:8672 starts Timer3 setup
- firmware/disasm/main/gpdasm_output.asm:8692 is the tight wait on PIR2.TMR3IF

The failing behavior is:
- CONTROL starts sending frames
- MAIN RX write pointer advances
- MAIN never progresses past the Timer3 wait in native-ring mode
- MAIN does not emit the expected BF... reply traffic

The mailbox path already hides this with a shim, so the remaining issue is specifically simulation fidelity in the native-ring / raw-main path.

Relevant repo files:
- stock MAIN disassembly:
  - firmware/disasm/main/gpdasm_output.asm
- MAIN harnesses:
  - src/dlcp_fw/sim/main_gpsim.py
  - src/dlcp_fw/sim/main_gpsim_timer3.py
  - src/dlcp_fw/sim/chain_gpsim.py
  - src/dlcp_fw/sim/manifests.py
- repo-local gpsim fork:
  - vendor/gpsim-0.32.1-xtc/
- current failing / relevant tests:
  - tests/sim/test_main_gpsim_timer3_compare.py
  - tests/sim/test_chain_gpsim_waiting.py
  - tests/sim/test_chain_gpsim_v25_recovery.py
  - tests/sim/test_chain_gpsim_v25_v162b_recovery.py

Authoritative datasheet sections to use:

1. Clock / instruction timing for MAIN
- firmware/reference/39632e.md:2473
  - PIC18 instruction cycle section
- firmware/reference/39632e.md:2481
  - one instruction cycle = four Q cycles
- firmware/reference/39632e.md:11469
  - CONFIG1L decode for CPUDIV and PLLDIV
- firmware/reference/39632e.md:11489
  - CONFIG1H decode for FOSC=ECPIO

Derived MAIN timing already validated in repo docs:
- external clock into OSC1/CLKI: 12 MHz
- PLL input after PLLDIV: 4 MHz
- PLL output: 96 MHz
- CPU/system Fosc after CPUDIV: 16 MHz
- instruction clock = Fosc/4 = 4 MHz
- Tcy = 250 ns

See:
- docs/analysis/MAIN_CLOCK_TIMING.md

2. Timer3 module behavior
- firmware/reference/39632e.md:5645
  - T3CON register, RD16, prescaler, TMR3CS, TMR3ON
- firmware/reference/39632e.md:5663
  - Timer3 operation; when TMR3CS=0 Timer3 increments on every internal instruction cycle (FOSC/4)
- firmware/reference/39632e.md:5705
  - Timer3 16-bit read/write mode; prescaler only clears on writes to TMR3L
- firmware/reference/39632e.md:5719
  - Timer3 overflow interrupt; TMR3IF in PIR2<1>, TMR3IE in PIE2<1>
- firmware/reference/39632e.md:5723
  - CCP2 special event trigger resets Timer3 but does not set TMR3IF

3. Interrupt register semantics
- firmware/reference/39632e.md:4264
  - PIR2 register
- firmware/reference/39632e.md:4273
  - TMR3IF semantics
- firmware/reference/39632e.md:4339
  - PIE2 register
- firmware/reference/39632e.md:4350
  - TMR3IE semantics
- firmware/reference/39632e.md:4388
  - IPR2 register
- firmware/reference/39632e.md:4400
  - TMR3IP semantics

4. Exact SFR addresses
- firmware/reference/39632e.md:2699
  - T3CON = F91h
  - TMR3L = F92h
  - TMR3H = F93h
  - SPBRG = F8Fh
  - SPBRGH = F90h
  - PIR2 = F81h
  - PIE2 = F80h
  - IPR2 = F82h

5. Related serial / MSSP timing context
- firmware/reference/39632e.md:9714
  - EUSART BRG section
- firmware/reference/39632e.md:9734
  - baud rate formulas table
- firmware/reference/39632e.md:9741
  - note: blank row in Markdown conversion; verify against PDF if needed
- firmware/reference/39632e.md:8581
  - I2C master clock formula FOSC/(4 * (SSPADD + 1))
- firmware/reference/39632e.md:9124
  - MSSP BRG counts down twice per Tcy in I2C master mode

6. Pin mapping if needed for external Timer3 source analysis
- firmware/reference/39632e.md:680
  - RC0/T13CKI
  - RC1/T1OSI
  - RC6/TX
  - RC7/RX

Specific firmware behavior to reconcile with the simulator:

- MAIN Timer3 wait loop:
  - firmware/disasm/main/gpdasm_output.asm:8674
    - branches on OSCCON.SCS1 to choose preload
  - firmware/disasm/main/gpdasm_output.asm:8677
    - writes TMR3H = 0xFC in one branch
  - firmware/disasm/main/gpdasm_output.asm:8683
    - writes TMR3H = 0xF8 in the other branch
  - firmware/disasm/main/gpdasm_output.asm:8689
    - writes TMR3L (which also clears the prescaler per datasheet)
  - firmware/disasm/main/gpdasm_output.asm:8690
    - clears PIR2.TMR3IF
  - firmware/disasm/main/gpdasm_output.asm:8694
    - spins until PIR2.TMR3IF is set

- MAIN UART init:
  - firmware/disasm/main/gpdasm_output.asm:8821
  - establishes BRGH=1, BRG16=1, SPBRG=0x7F -> 31,250 baud with Fosc=16 MHz

- MAIN MSSP/I2C init:
  - firmware/disasm/main/gpdasm_output.asm:6178
  - SSPADD=0x77 -> about 33.33 kHz with Fosc=16 MHz

What you need to determine:

1. Is the remaining gap a bug or incompleteness in vendor/gpsim-0.32.1-xtc PIC18F2455 Timer3 simulation?
2. Or is the issue in the repo harness, for example:
   - bad Timer3 setup assumptions,
   - wrong prompt/pty handling in Timer3 probes,
   - native-ring execution path not allowing the right interrupt/flag behavior,
   - bad interaction between overlays and real Timer3 state?
3. If the simulator is missing PIC18F2455 Timer3 behavior, implement the missing support in the local gpsim fork.
4. If the simulator is correct and the harness is wrong, fix the harness.

Constraints:

- Use the repo-local gpsim fork / resolver, not the system gpsim.
- Do not rely on firmware/reference/39632e.txt; it has been removed.
- Do not place firmware or simulation helper code below 0x1000. This repository treats <0x1000 as off-limits.
- Do not change release firmware images just to make simulation pass.
- Prefer fixing simulator or harness fidelity over adding more semantic shims.
- If you must keep a shim temporarily, isolate it and document exactly why it is still needed.

Required deliverables:

1. Root-cause explanation:
   - what exactly is missing or wrong today
   - why it breaks Timer3/native-ring MAIN progress
   - whether the fix belongs in gpsim core or the repo harness

2. Implementation:
   - code changes in the gpsim fork and/or repo harness
   - no new dependence on removed 39632e.txt

3. Tests:
   - update/add tests to lock in the fix

4. Docs:
   - update any docs that describe the Timer3/native-ring gap or current simulation limitations
   - keep AGENTS.md in sync if file paths change

Acceptance criteria:

- tests/sim/test_main_gpsim_timer3_compare.py passes in the intended non-shim mode
- tests/sim/test_chain_gpsim_waiting.py passes without the current Timer3/native-ring stall
- tests/sim/test_chain_gpsim_v25_recovery.py meaningfully runs past the old Timer3 wait bottleneck
- tests/sim/test_chain_gpsim_v25_v162b_recovery.py meaningfully runs past the old Timer3 wait bottleneck
- no new writes or helper placements below 0x1000

Suggested execution order:

1. Reproduce the current Timer3 stall with the existing tests and/or a minimal MAIN-only probe.
2. Inspect current PIC18F2455 Timer3 behavior in vendor/gpsim-0.32.1-xtc against the datasheet sections above.
3. Compare actual simulator register/flag behavior with the stock code’s expectations in function_079.
4. Implement the minimal correct fix.
5. Re-run the Timer3 compare test.
6. Re-run the chain / reconnect tests.
7. Update docs with the final diagnosis and any remaining limitations.

When citing the datasheet in your response, prefer:
- firmware/reference/39632e.pdf as authoritative
- firmware/reference/39632e.md for line-stable local citations

Do not answer with only analysis. Carry the work through implementation, tests, and a concise result summary.
```
