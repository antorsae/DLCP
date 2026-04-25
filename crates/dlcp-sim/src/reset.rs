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
//! * It does NOT initialize every SFR to its POR value (e.g.
//!   TXSTA=0x02, RCSTA=0x00x).  That belongs to the
//!   peripheral modules (P2) which know their own reset
//!   defaults; the reset module only touches the SFRs that the
//!   reset-source table explicitly mutates (RCON + STKPTR
//!   sticky flags).  P1.7's hex loader + P2's peripheral
//!   constructors compose to bring everything else to POR.
//! * It does NOT apply the configuration words.  CONFIG bits
//!   like STVREN, BOREN, IPEN, WDTEN are parsed in P1.7; the
//!   reset path consumes them as preconditions.
//! * It does NOT model power-down (Sleep) or oscillator
//!   start-up timers.  Those belong to the oscillator
//!   peripheral (P2.9).

#![allow(dead_code, reason = "P1.6 dispatcher; consumed by P1.7 boot path + P1.2 RESET instruction")]

use crate::core::Core;
use crate::memory::Address;
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
    /// preserved; stack state preserved.
    Mclr,
    /// Watchdog Time-out reset (not the wake-from-sleep case;
    /// see DS39632E §25.2).  RCON.TO forced to 0; other bits
    /// preserved.
    Wdt,
    /// `RESET` instruction.  RCON.RI forced to 0; other bits
    /// preserved; stack state preserved (PIC18 RESET does not
    /// clear the stack).
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
        }
        ResetSource::BrownOut
        | ResetSource::Mclr
        | ResetSource::Wdt
        | ResetSource::ResetInstruction => {
            // Stack preserved on these resets (DS39632E
            // Table 4-1: STKFUL=u, STKUNF=u for all of them).
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
    fn mclr_preserves_stack() {
        let (mut core, mut stack) = fresh_core_and_stack();
        stack.push(0x4576);
        stack.push(0x4FE0);
        apply_reset(&mut core, &mut stack, ResetSource::Mclr);
        assert_eq!(stack.depth(), 2);
        assert_eq!(stack.top(), 0x4FE0);
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
