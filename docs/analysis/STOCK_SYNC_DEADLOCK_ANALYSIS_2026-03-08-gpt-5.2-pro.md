Deadlock / desync risks I can confirm in stock 2.3 + 1.4

  - CONTROL has a true “wait forever” state: label_216 spins until flags.bit1 becomes 1, with no timeout/backoff (firmware/disasm/control/
    v1.4_disasm.asm:3236). If MAIN stops producing the keepalive/status frames, CONTROL will sit here (“WAITING FOR DLCP”).
  - MAIN has multiple hard blocking MSSP/I2C polling loops with no timeout/recovery (examples: wait for SSPCON2.SEN to clear at 0x002288,
    SSPCON2.PEN at 0x00231A, SSPSTAT.BF at 0x003EB8 and 0x00466A): firmware/disasm/main/gpdasm_output.asm:3098, firmware/disasm/main/
    gpdasm_output.asm:3175, firmware/disasm/main/gpdasm_output.asm:7633, firmware/disasm/main/gpdasm_output.asm:8979.
  - MAIN can also hang in UART TX: function_111 spins on TXSTA.TRMT with no timeout (firmware/disasm/main/gpdasm_output.asm:9401).
  - MAIN’s I2C write routine checks SSPCON1.WCOL and bails, but never clears WCOL anywhere; one write collision can leave DSP/I2C updates
    permanently broken until reset (firmware/disasm/main/gpdasm_output.asm:7633).
  - The gpsim harness has to patch these exact loops to run at all (src/dlcp_fw/sim/manifests.py:559, used by default in scripts/
    gpsim_tui_simulator.py:568)—that’s the same “spin forever if the peripheral never completes” failure mode you can hit on hardware if the I2C
    bus wedges.

  Watchdog (WDT) reality

  - Datasheet: CONFIG2H contains WDTPS and WDTEN (firmware/reference/39632e.txt:46958); WDT behavior and WDTCON.SWDTEN are described in the WDT
    section (firmware/reference/39632e.txt:47853).
  - Stock MAIN has CONFIG2H=0x1E → WDTEN=0 (off, SW-controlled) and WDTPS=0xF (1:32768). Stock CONTROL has CONFIG2H=0x00 → WDTEN=0, WDTPS=0
    (1:1). Neither disassembly shows any WDTCON access, so WDT stays off in practice → a deadlock won’t self-recover.

  How this matches your symptom

  - Volume updates on MAIN are implemented as TAS3108 I2C writes; if MAIN wedges in those polling loops (or gets stuck in a latched I2C error
    like WCOL), CONTROL can still “work” while MAIN doesn’t actually change volume (docs/analysis/CONTROL_UNIT_ANALYSIS.md:316). If a MAIN fully
    wedges, CONTROL eventually falls into the infinite WAIT loop.

  Safest fix order (what I’d patch first)

  1. MAIN: enable WDT via WDTCON.SWDTEN=1 early in init (CONFIG already sets a long postscale), so true deadlocks self-recover.
  2. MAIN: add bounded timeouts to the I2C polling loops and on timeout either reset MSSP+retry or force a soft reset (explicit reset helper
     exists at firmware/disasm/main/gpdasm_output.asm:9450).
  3. MAIN: handle WCOL properly (clear it, flush/STOP, retry or reset) to fix the “runs but no DSP updates” failure mode.
