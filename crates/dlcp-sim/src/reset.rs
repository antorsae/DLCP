//! PIC18 reset-source dispatcher.
//!
//! Each documented reset source (POR, BOR, MCLR, WDT, RESET
//! instruction, stack overflow / underflow with STVREN=1) sets
//! a different combination of bits in RCON / STKPTR per
//! DS39632E Table 4-1 ("Status Bits, Their Significance and the
//! Initialization Conditions for RCON Register") and §5.4.2
//! ("Stack Full and Underflow Resets").  This module's job is
//! to take a [`ResetSource`] and a `&mut Core` + `&mut Stack`
//! and apply the right state transition; whether to actually
//! reset (e.g. stack overflow only resets when STVREN=1) is the
//! caller's responsibility (the executor in P1.2 dispatch +
//! P1.7 config-bit parser determine STVREN).
//!
//! ### What this module does NOT do
//!
//! * It does NOT apply the configuration words.  CONFIG bits
//!   like STVREN, BOREN, IPEN, WDTEN are parsed in P1.7; the
//!   reset path consumes them as preconditions.
//! * It does NOT model power-down (Sleep) or oscillator
//!   start-up timers.  Those belong to the oscillator
//!   peripheral (P2.9).
//! * It does NOT model SFRs that depend on dynamic device state
//!   the reset path has no way to know (e.g. OSCCON's IOFS bit
//!   that flips once HFINTOSC stabilises -- a few hundred Tcy
//!   after POR per DS40001303H §2.5.2.1).  Those are P2 work.
//!
//! ### What this module DOES do (extended in P1.8d)
//!
//! POR additionally programs the SFR window with the full
//! K20 / 2455 power-on initial values per their datasheets'
//! "Initialization Conditions for All Registers" tables (K20:
//! DS40001303H Table 4-4 p.56-60; 2455: DS39632E Table 4-2).
//! Without this the V1.71 / V2.3 boot paths read 0 for SFRs
//! the silicon brings up non-zero (TRIS = 1s for all-input
//! POR, ANSEL = 1s for all-analog, T0CON = 1s, IPRx = 1s,
//! etc.) and immediately diverge.

#![allow(dead_code, reason = "P1.6 dispatcher; consumed by P1.7 boot path + P1.2 RESET instruction")]

use crate::core::Core;
use crate::memory::{Address, Variant};
use crate::stack::Stack;

/// `RCON` SFR address on both PIC18 variants.
pub const RCON_ADDR: u16 = 0xFD0;

/// `RCON.RI` (RESET Instruction Flag), bit 4.  `0` = the RESET
/// instruction last fired; `1` otherwise.
pub const RCON_RI: u8 = 0x10;

/// `RCON.TO` (Watchdog Time-out Flag), bit 3.  `0` = WDT
/// timed out; `1` otherwise.
pub const RCON_TO: u8 = 0x08;

/// `RCON.PD` (Power-down Detection Flag), bit 2.  `0` = SLEEP
/// instruction last executed; `1` otherwise.
pub const RCON_PD: u8 = 0x04;

/// `RCON.POR` (Power-on Reset Flag), bit 1.  `0` = POR fired
/// since the last software-set; `1` otherwise.  Cleared only
/// by POR; reasserted by software.
pub const RCON_POR: u8 = 0x02;

/// `RCON.BOR` (Brown-out Reset Flag), bit 0.  `0` = BOR fired
/// since the last software-set; `1` otherwise.  Cleared only by
/// BOR (or POR via config); reasserted by software.
pub const RCON_BOR: u8 = 0x01;

/// What initiated this reset.  Drives the RCON / STKPTR bit
/// transitions per DS39632E Table 4-1.
#[derive(Copy, Clone, Eq, PartialEq, Debug, Hash)]
pub enum ResetSource {
    /// Power-On Reset.  Applies the strictest POR state: clears
    /// RCON.POR and RCON.BOR, sets RI/TO/PD high, clears the
    /// stack and its sticky flags, and zeros all 4096 bytes of
    /// data memory before the reset vector fires.
    PowerOn,
    /// Brown-out Reset.  Same RCON updates as POR except
    /// RCON.POR is preserved; STKFUL/STKUNF preserved (DS39632E
    /// §5.4.2 says STKFUL is cleared only by POR).
    BrownOut,
    /// External MCLR.  RCON.TO is forced to 1; other RCON bits
    /// preserved.  Stack pointer is reset to 0 per DS39632E
    /// §5.4 ("On Reset, the Stack Pointer value will be zero")
    /// while sticky flags STKFUL/STKUNF and slot data are
    /// preserved (Table 4-1: STKFUL=u, STKUNF=u for MCLR).
    Mclr,
    /// Watchdog Time-out reset (not the wake-from-sleep case;
    /// see DS39632E §25.2).  RCON.TO forced to 0; other bits
    /// preserved.  Stack pointer reset to 0; flags + slot data
    /// preserved (same as MCLR).
    Wdt,
    /// `RESET` instruction.  RCON.RI forced to 0; other bits
    /// preserved.  Stack pointer reset to 0; flags + slot data
    /// preserved (same as MCLR).
    ResetInstruction,
    /// Stack Full Reset, fires only when STVREN=1 and a CALL/
    /// RCALL/interrupt push fills the 31st slot.  STKPTR depth
    /// is forced to 0; STKFUL stays set (per DS39632E §5.4.2).
    /// RCON unchanged.
    StackFull,
    /// Stack Underflow Reset, fires only when STVREN=1 and a
    /// RETURN/RETFIE/POP is issued at depth=0.  STKUNF stays
    /// set.  RCON unchanged.
    StackUnderflow,
}

/// Apply a reset.  Mutates `core` and `stack` to the post-reset
/// state documented in DS39632E Table 4-1 + §5.4.2.
///
/// PC is set to the reset vector (0x0000) for every reset type;
/// see DS39632E §4.0.  The caller is then expected to start
/// executing from there on the next instruction-fetch cycle.
pub fn apply_reset(core: &mut Core, stack: &mut Stack, source: ResetSource) {
    // PC always returns to the reset vector.  DS39632E §4.0:
    // "Reset events vector all PIC18 devices back to address
    // 0000h, where execution restarts."
    core.set_pc(0);

    let rcon = core.memory.read_raw(Address::from_raw(RCON_ADDR));
    let rcon = match source {
        // POR: RI=1, TO=1, PD=1, POR=0, BOR=0.
        ResetSource::PowerOn => {
            (rcon & !(RCON_POR | RCON_BOR)) | RCON_RI | RCON_TO | RCON_PD
        }
        // BOR: RI=1, TO=1, PD=1, POR=u, BOR=0.
        ResetSource::BrownOut => {
            (rcon & !RCON_BOR) | RCON_RI | RCON_TO | RCON_PD
        }
        // MCLR: RI=u, TO=1, PD=u, POR=u, BOR=u.
        ResetSource::Mclr => rcon | RCON_TO,
        // WDT: TO=0, others u.  (This is the WDT-while-running
        // reset; the WDT-during-Sleep wake-up clears PD too,
        // which the executor handles separately in P1.7.)
        ResetSource::Wdt => rcon & !RCON_TO,
        // RESET instruction: RI=0, others u.
        ResetSource::ResetInstruction => rcon & !RCON_RI,
        // Stack overflow / underflow: RCON unchanged; only
        // STKPTR latches change.
        ResetSource::StackFull | ResetSource::StackUnderflow => rcon,
    };
    core.memory.write_raw(Address::from_raw(RCON_ADDR), rcon);

    // Stack / STKPTR transitions.
    match source {
        ResetSource::PowerOn => {
            // Full stack wipe: depth=0, slots zeroed, both
            // sticky flags cleared.
            stack.por_reset();
            // POR also zeroes ALL data memory — even though
            // that's nominally a peripheral concern, the reset
            // module owns the "everything is zero on day one"
            // contract because no peripheral has run yet.
            for byte in core.memory.as_mut_slice() {
                *byte = 0;
            }
            // RCON's POR-reset value still needs to be written
            // back: clearing the slice above blew away the
            // bits we just composed.  Re-write RCON to the
            // post-POR state so RI/TO/PD/POR/BOR are correct.
            core.memory.write_raw(
                Address::from_raw(RCON_ADDR),
                RCON_RI | RCON_TO | RCON_PD,
            );
            // SFR POR initialisation table (variant-specific).
            apply_por_sfr_defaults(core);
        }
        ResetSource::BrownOut
        | ResetSource::Mclr
        | ResetSource::Wdt
        | ResetSource::ResetInstruction => {
            // DS39632E §5.4 ("On Reset, the Stack Pointer
            // value will be zero") + Table 4-1 (STKFUL=u,
            // STKUNF=u for all of these): the pointer drops
            // to 0 on these resets, but the sticky flags AND
            // the slot data are preserved across the reset.
            // A previous CALL/RCALL pushed onto the stack
            // remains in slot[depth_pre_reset-1] and can be
            // read via TOSU/H/L after firmware writes a new
            // depth into STKPTR.
            stack.reset_pointer_preserve_flags();
        }
        ResetSource::StackFull => {
            // Depth → 0; STKFUL stays set.  Slot data preserved.
            stack.reset_for_stack_full();
        }
        ResetSource::StackUnderflow => {
            stack.reset_for_stack_underflow();
        }
    }
}

/// Apply the variant-specific SFR power-on initial values.
/// Runs after the POR memory wipe, so any non-zero default the
/// silicon brings up at POR is restored.
///
/// K20: DS40001303H Table 4-4 ("Initialization Conditions for All
/// Registers", p.56-60) + Table 5-2 footnotes for 28-pin masking.
/// Only entries that are non-zero at POR are listed -- everything
/// else is already 0 from the memory wipe above.
///
/// 2455: not yet wired.  When the 2455 isa-parity gate lands,
/// add a parallel match arm with DS39632E Table 4-2's defaults.
fn apply_por_sfr_defaults(core: &mut Core) {
    match core.variant() {
        Variant::Pic18F25K20 => apply_k20_por_sfr_defaults(core),
        Variant::Pic18F2455 => {
            // P1.8d covers K20 only; the 2455 POR table will land
            // alongside the V2.3 MAIN parity gate.
        }
    }
}

/// PIC18F25K20 POR/BOR SFR initial values.
///
/// Source: DS40001303H Table 4-4 (p.56-60).  Each entry is
/// `(addr, value)` where `value` is the post-POR byte after
/// applying any 28-pin / oscillator-mode footnote masks
/// documented in Table 5-2 footnotes 2 and 5.
///
/// Where Table 4-4 lists `xxxx xxxx` (unknown / undefined) the
/// register is omitted -- the POR memory wipe leaves it 0,
/// which is what gpsim's K20 model also reports.
fn apply_k20_por_sfr_defaults(core: &mut Core) {
    // (addr, por_value, datasheet_note)
    //
    // Bit-pattern translation rules:
    //   * `1` bit  -> 1 in the byte
    //   * `0` bit  -> 0
    //   * `-` bit  -> 0  (unimplemented; reads as 0 per legend)
    //   * `q` bit  -> 0  (condition-dependent; the post-POR
    //                     value is 0 for the bits relevant here;
    //                     OSCCON's IOFS/SCS bits stay 0 until
    //                     HFINTOSC stabilises -- a P2 concern)
    const K20_POR: &[(u16, u8)] = &[
        // INTCON2: RBPU=1, INTEDG0/1/2=1, TMR0IP=1, RBIP=1.
        // Bits 3 (-) and 1 (-) unimplemented -> 0.
        (0xFF1, 0xF5),
        // INTCON3: INT2IP=1, INT1IP=1, others 0.  Bits 5 (-) and
        // 2 (-) unimplemented.
        (0xFF0, 0xC0),
        // T0CON: all 1s at POR (timer disabled, prescaler maxed).
        (0xFD5, 0xFF),
        // OSCCON: IRCF<2:0>=011 (1 MHz nominal HFINTOSC tap).
        // OSTS/IOFS/SCS<1:0> are q-bits and stay 0 until the
        // oscillator-stabilisation timer fires -- modelled in
        // P2's oscillator peripheral, not here.  gpsim's K20
        // model writes 0x40 by cycle 10 because it triggers a
        // post-POR IRCF auto-tune to the configured HFINTOSC
        // frequency; documented as a known transient divergence
        // until P2 lands the equivalent state machine.
        (0xFD3, 0x30),
        // HLVDCON: HLVDL<3:0>=0101 (default HLV detect = 2.0V
        // typical per Reg 21-1).  Bit 6 (-) unimplemented.
        (0xFD2, 0x05),
        // PR2: Timer2 period match value = 0xFF.
        (0xFCB, 0xFF),
        // TXSTA: TRMT=1 (TSR empty).  TRMT is hardware-driven
        // read-only; the SFR write mask in exec.rs preserves it
        // across SW writes.
        (0xFAC, 0x02),
        // PSTRCON: STRA=1 (single-output PWM steered to P1A).
        // Bits 7..4 (-) unimplemented; STRSYNC bit 4 = 0.
        (0xFB9, 0x01),
        // BAUDCON: RCIDL=1 (receiver idle).  Bit 2 (-) unimpl.
        (0xFB8, 0x40),
        // IPR1: all peripheral interrupt priorities high (=1).
        // PIC18F2XK20 (28-pin) has bit 7 (PSPIP) unimplemented
        // per Table 5-2 footnote 2 -> 0x7F not 0xFF.
        (0xF9F, 0x7F),
        // IPR2: all bits 1.
        (0xFA2, 0xFF),
        // TRISA: all-input.  Bit 7 (RA7/OSC1) is disabled in
        // INTOSC modes per Table 5-2 footnote 5 and reads 0;
        // V1.71's CONFIG selects HFINTOSC, so bit 7 = 0 and
        // POR-effective TRISA is 0x7F.  When the 2455 / non-
        // INTOSC config lands this needs to consult the parsed
        // CONFIG bits (Task #14 follow-up).
        (0xF92, 0x7F),
        // TRISB: all-input.
        (0xF93, 0xFF),
        // TRISC: all-input.
        (0xF94, 0xFF),
        // ANSEL / ANSELH: all-analog (PORTA/B start as analog).
        // ANSELH is conditional on PBADEN config bit per Note 6;
        // V1.71's CONFIG3H has PBADEN=1 -> 0x1F.
        (0xF7E, 0xFF),
        (0xF7F, 0x1F),
        // WPUB: weak pull-ups enabled.
        (0xF7C, 0xFF),
        // SLRCON: slew-rate control = normal (1) for SLRA/B/C.
        // 28-pin omits SLRD/SLRE per Table 5-2 footnote 2 -> 0x07.
        (0xF78, 0x07),
        // SSPMSK: I2C address mask = all 1s.
        (0xF77, 0xFF),
    ];

    for (addr, value) in K20_POR {
        core.memory
            .write_raw(Address::from_raw(*addr), *value);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::memory::Variant;

    fn rcon_byte(core: &Core) -> u8 {
        core.memory.read_raw(Address::from_raw(RCON_ADDR))
    }

    fn fresh_core_and_stack() -> (Core, Stack) {
        (Core::new(Variant::Pic18F2455), Stack::new())
    }

    // ----- POR -----

    #[test]
    fn por_zeros_pc_and_sets_rcon() {
        let (mut core, mut stack) = fresh_core_and_stack();
        core.set_pc(0x4576);
        apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
        assert_eq!(core.pc(), 0);
        // RI=1, TO=1, PD=1, POR=0, BOR=0
        assert_eq!(
            rcon_byte(&core),
            RCON_RI | RCON_TO | RCON_PD,
        );
    }

    #[test]
    fn por_zeroes_data_memory_and_clears_stack() {
        let (mut core, mut stack) = fresh_core_and_stack();
        // Dirty data memory + stack
        core.memory.write_raw(Address::from_raw(0x100), 0x42);
        for _ in 0..5 {
            stack.push(0x1234);
        }
        apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
        // Memory cleared (except RCON which we explicitly set)
        assert_eq!(core.memory.read_raw(Address::from_raw(0x100)), 0);
        // Stack cleared
        assert_eq!(stack.depth(), 0);
        assert!(!stack.overflow());
        assert!(!stack.underflow());
    }

    // ----- BOR -----

    #[test]
    fn bor_sets_rcon_with_por_preserved() {
        let (mut core, mut stack) = fresh_core_and_stack();
        // Pre-BOR RCON has POR=1 (set by software after a prior POR
        // — typical firmware idiom).
        core.memory.write_raw(Address::from_raw(RCON_ADDR), RCON_POR);
        apply_reset(&mut core, &mut stack, ResetSource::BrownOut);
        let rcon = rcon_byte(&core);
        // RI=1, TO=1, PD=1, BOR=0; POR preserved.
        assert!(rcon & RCON_RI != 0);
        assert!(rcon & RCON_TO != 0);
        assert!(rcon & RCON_PD != 0);
        assert!(rcon & RCON_BOR == 0);
        assert!(rcon & RCON_POR != 0);
    }

    // ----- MCLR -----

    #[test]
    fn mclr_only_forces_to_high() {
        let (mut core, mut stack) = fresh_core_and_stack();
        // Set RCON to a recognisable pattern: TO=0 (post-WDT) plus
        // some user bits.
        core.memory.write_raw(Address::from_raw(RCON_ADDR), 0x80);
        apply_reset(&mut core, &mut stack, ResetSource::Mclr);
        let rcon = rcon_byte(&core);
        // TO forced to 1; bit 7 (IPEN) preserved.
        assert!(rcon & RCON_TO != 0);
        assert!(rcon & 0x80 != 0);
    }

    #[test]
    fn mclr_zeros_stkptr_but_preserves_flags_and_slot_data() {
        // DS39632E §5.4: "On Reset, the Stack Pointer value
        // will be zero."  Table 4-1: STKFUL=u, STKUNF=u for
        // MCLR.  So depth → 0 but flags + slot data persist.
        let (mut core, mut stack) = fresh_core_and_stack();
        stack.push(0x4576);
        stack.push(0x4FE0);
        apply_reset(&mut core, &mut stack, ResetSource::Mclr);
        assert_eq!(stack.depth(), 0);
        // Slot data preserved — firmware can pull stored bytes
        // back via TOSU/TOSH/TOSL after writing STKPTR.depth.
        stack.write_stkptr(2);
        assert_eq!(stack.depth(), 2);
        assert_eq!(stack.top(), 0x4FE0);
    }

    #[test]
    fn mclr_preserves_underflow_flag() {
        // STKUNF is sticky and per DS39632E Table 4-1
        // (STKUNF=u for MCLR) it survives across an MCLR
        // reset.  Set the flag on the same stack we then
        // reset, then verify it's still asserted.
        let (mut core, mut stack) = fresh_core_and_stack();
        // Pop on empty to latch STKUNF.
        let _ = stack.pop();
        assert!(stack.underflow());
        // Push something on top so depth is non-zero pre-reset
        // (forces the depth-zeroing transition to actually
        // happen; without this depth is already 0 and the test
        // wouldn't exercise the change).
        stack.push(0x1000);
        assert_eq!(stack.depth(), 1);
        apply_reset(&mut core, &mut stack, ResetSource::Mclr);
        assert_eq!(stack.depth(), 0);
        assert!(stack.underflow());
    }

    #[test]
    fn mclr_preserves_overflow_flag() {
        let (mut core, mut stack) = fresh_core_and_stack();
        for i in 0..31 {
            stack.push(0x100 + i as u32);
        }
        // STKFUL latched.
        assert!(stack.overflow());
        apply_reset(&mut core, &mut stack, ResetSource::Mclr);
        // Pointer back to 0; STKFUL still latched.
        assert_eq!(stack.depth(), 0);
        assert!(stack.overflow());
    }

    #[test]
    fn bor_zeros_stkptr_but_preserves_flags_and_slot_data() {
        let (mut core, mut stack) = fresh_core_and_stack();
        stack.push(0x4576);
        stack.push(0x4FE0);
        for _ in 0..31 {
            // Force STKFUL latched so we can confirm survival.
            stack.push(0);
        }
        assert!(stack.overflow());
        apply_reset(&mut core, &mut stack, ResetSource::BrownOut);
        assert_eq!(stack.depth(), 0);
        assert!(stack.overflow());
    }

    #[test]
    fn wdt_zeros_stkptr() {
        let (mut core, mut stack) = fresh_core_and_stack();
        stack.push(0x1000);
        apply_reset(&mut core, &mut stack, ResetSource::Wdt);
        assert_eq!(stack.depth(), 0);
    }

    #[test]
    fn reset_instruction_zeros_stkptr() {
        let (mut core, mut stack) = fresh_core_and_stack();
        stack.push(0x1000);
        stack.push(0x2000);
        apply_reset(&mut core, &mut stack, ResetSource::ResetInstruction);
        assert_eq!(stack.depth(), 0);
    }

    // ----- WDT -----

    #[test]
    fn wdt_clears_to() {
        let (mut core, mut stack) = fresh_core_and_stack();
        core.memory.write_raw(Address::from_raw(RCON_ADDR), 0xFF);
        apply_reset(&mut core, &mut stack, ResetSource::Wdt);
        let rcon = rcon_byte(&core);
        assert_eq!(rcon & RCON_TO, 0);
        // Other bits preserved
        assert_eq!(rcon | RCON_TO, 0xFF);
    }

    // ----- RESET instruction -----

    #[test]
    fn reset_instruction_clears_ri() {
        let (mut core, mut stack) = fresh_core_and_stack();
        core.memory.write_raw(Address::from_raw(RCON_ADDR), 0xFF);
        apply_reset(&mut core, &mut stack, ResetSource::ResetInstruction);
        let rcon = rcon_byte(&core);
        assert_eq!(rcon & RCON_RI, 0);
        // Other bits preserved
        assert_eq!(rcon | RCON_RI, 0xFF);
    }

    // ----- Stack Full / Underflow -----

    #[test]
    fn stack_full_reset_zeros_depth_keeps_stkful() {
        let (mut core, mut stack) = fresh_core_and_stack();
        for i in 0..31 {
            stack.push(0x100 + i as u32);
        }
        // STKFUL is now set (the 31st push set it).
        assert!(stack.overflow());
        apply_reset(&mut core, &mut stack, ResetSource::StackFull);
        // Stack depth back to 0 but STKFUL stays asserted (per
        // DS39632E §5.4.2).
        assert_eq!(stack.depth(), 0);
        assert!(stack.overflow());
        assert!(!stack.underflow());
    }

    #[test]
    fn stack_full_reset_does_not_touch_rcon() {
        let (mut core, mut stack) = fresh_core_and_stack();
        core.memory.write_raw(Address::from_raw(RCON_ADDR), 0xA5);
        apply_reset(&mut core, &mut stack, ResetSource::StackFull);
        assert_eq!(rcon_byte(&core), 0xA5);
    }

    #[test]
    fn stack_underflow_reset_latches_stkunf() {
        let (mut core, mut stack) = fresh_core_and_stack();
        // Pop on empty to set STKUNF.
        let _ = stack.pop();
        assert!(stack.underflow());
        apply_reset(&mut core, &mut stack, ResetSource::StackUnderflow);
        assert_eq!(stack.depth(), 0);
        assert!(stack.underflow());
    }

    #[test]
    fn stack_underflow_reset_does_not_touch_rcon() {
        let (mut core, mut stack) = fresh_core_and_stack();
        core.memory.write_raw(Address::from_raw(RCON_ADDR), 0x33);
        apply_reset(&mut core, &mut stack, ResetSource::StackUnderflow);
        assert_eq!(rcon_byte(&core), 0x33);
    }

    // ----- Every reset source returns PC to 0 -----

    #[test]
    fn every_reset_source_returns_pc_to_zero() {
        let sources = [
            ResetSource::PowerOn,
            ResetSource::BrownOut,
            ResetSource::Mclr,
            ResetSource::Wdt,
            ResetSource::ResetInstruction,
            ResetSource::StackFull,
            ResetSource::StackUnderflow,
        ];
        for src in sources {
            let (mut core, mut stack) = fresh_core_and_stack();
            core.set_pc(0x1234);
            apply_reset(&mut core, &mut stack, src);
            assert_eq!(core.pc(), 0, "PC should be 0 after {src:?}");
        }
    }
}
