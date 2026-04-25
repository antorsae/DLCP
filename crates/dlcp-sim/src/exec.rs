//! Cycle-accurate PIC18 instruction executor.
//!
//! Drives [`crate::core::Core`] forward one instruction at a time
//! by:
//!
//!   1. Fetching the 16-bit word at `Core::pc()` from the flash
//!      buffer (and the next word too — required by the decoder
//!      for the four 2-word ops `CALL`, `GOTO`, `MOVFF`, `LFSR`).
//!   2. Decoding via [`crate::isa::decode`].
//!   3. Advancing the PC by the decoded byte count (2 or 4).
//!   4. Dispatching over [`crate::isa::Instruction`] and applying
//!      the instruction's RAM / SFR / stack / cycle-counter side
//!      effects.
//!   5. Returning the Tcy cost (1 / 2 / 3) to the caller, which
//!      P3's chain scheduler converts into the universal-tick
//!      domain.
//!
//! ## Coverage roll-out
//!
//! P1.8b lands the executor incrementally — one or two
//! instruction categories per commit so the per-commit codex
//! review can audit each transition (STATUS-flag fidelity,
//! Access-Bank routing, FSR indirect addressing, etc.) without
//! drowning.  Until the full 75-instruction set is wired,
//! unimplemented variants surface as
//! [`ExecError::Unimplemented`]; the dispatch's wildcard arm
//! shrinks with each commit and disappears entirely once every
//! variant is covered.
//!
//! Reference: DS39632E §26 (PIC18F2455 Instruction Set Summary,
//! Table 26-2) and DS41303G §25 (PIC18F25K20 instruction set —
//! byte-for-byte identical for every opcode this firmware uses).

#![allow(dead_code, reason = "P1.8b executor; consumed by P1.8c/d/e parity tests")]

use crate::core::Core;
use crate::isa::{Instruction, decode};
use crate::stack::Stack;

/// Fatal executor error.  Non-fatal conditions (skip-not-taken,
/// overflow flags, etc.) are signalled through STATUS / RCON
/// inside the model — only the cases below tear the run down.
#[derive(Copy, Clone, Eq, PartialEq, Debug)]
pub enum ExecError {
    /// PC is past the end of the variant's program memory and
    /// has nothing to fetch.  Real silicon wraps; the executor
    /// surfaces this loudly so a runaway test (typically a
    /// missing GOTO at the end of an inline test program) shows
    /// up instead of looping at PC=0 silently.
    PcOutOfBounds(u32),
    /// Decoder produced [`Instruction::Reserved`] — opcode bits
    /// don't match any documented PIC18 instruction.
    Reserved(u16),
    /// Instruction variant not yet wired into the dispatch.  Goes
    /// away as P1.8b lands more instruction categories; once the
    /// match is exhaustive this variant becomes unreachable.
    Unimplemented(Instruction),
}

/// Step the core by one instruction.  Returns the Tcy cost of
/// the instruction on success.
pub fn step(core: &mut Core, stack: &mut Stack) -> Result<u8, ExecError> {
    let _ = stack; // kept in the signature even though P1.8b's
    // initial NOP-only dispatch doesn't touch the stack — control-
    // flow instructions land in subsequent commits.

    let pc = core.pc();
    let pc_idx = pc as usize;
    let flash = core.flash();

    // PC must have at least one full word ahead.
    if pc_idx + 1 >= flash.len() {
        return Err(ExecError::PcOutOfBounds(pc));
    }
    let word1 = u16::from_le_bytes([flash[pc_idx], flash[pc_idx + 1]]);

    // The decoder also wants `word2`; if it can't be read
    // because we're at the very last word of flash, hand it the
    // all-ones sentinel per its docstring -- the decoder ignores
    // word2 for single-word instructions.  We then verify post-
    // decode that the instruction was actually single-word; a
    // synthetic word2 carried into a 2-word op (CALL, GOTO,
    // MOVFF, LFSR) would silently fabricate the continuation
    // bits, so refuse to execute and surface PcOutOfBounds.
    let word2_available = pc_idx + 3 < flash.len();
    let word2 = if word2_available {
        u16::from_le_bytes([flash[pc_idx + 2], flash[pc_idx + 3]])
    } else {
        0xFFFF
    };

    let (instr, byte_count) = decode(word1, word2);
    if byte_count == 4 && !word2_available {
        return Err(ExecError::PcOutOfBounds(pc));
    }
    core.set_pc(pc.wrapping_add(byte_count));

    match instr {
        Instruction::Nop => {
            core.advance_cycles(1);
            Ok(1)
        }
        // PIC18 hardware decodes a stray second-word continuation
        // (`1111 xxxx xxxx xxxx`) as NOP; mirror that behaviour
        // rather than erroring, since erased flash + a misaligned
        // jump can land on one and the firmware still expects to
        // recover.
        Instruction::NopContinuation { .. } => {
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::Reserved { word } => Err(ExecError::Reserved(word)),
        other => Err(ExecError::Unimplemented(other)),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::memory::Variant;

    fn k20_core_with_flash(prog: &[u8]) -> Core {
        let mut core = Core::new(Variant::Pic18F25K20);
        core.flash_mut()[..prog.len()].copy_from_slice(prog);
        core
    }

    // 0x0000 is the NOP encoding (`0000 0000 0000 0000`).
    const NOP_BYTES: [u8; 2] = [0x00, 0x00];

    #[test]
    fn step_nop_advances_pc_by_two_and_charges_one_cycle() {
        let mut core = k20_core_with_flash(&NOP_BYTES);
        let mut stack = Stack::new();

        let cycles = step(&mut core, &mut stack).expect("NOP must execute");
        assert_eq!(cycles, 1, "NOP costs 1 Tcy");
        assert_eq!(core.pc(), 0x0002);
        assert_eq!(core.cycles(), 1);
    }

    #[test]
    fn step_two_nops_in_a_row_advance_pc_and_cycles_monotonically() {
        let prog = [0x00, 0x00, 0x00, 0x00];
        let mut core = k20_core_with_flash(&prog);
        let mut stack = Stack::new();

        step(&mut core, &mut stack).unwrap();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.pc(), 0x0004);
        assert_eq!(core.cycles(), 2);
    }

    #[test]
    fn step_treats_nop_continuation_as_nop() {
        // `0xFFFF` decodes as NopContinuation; PIC18 silicon
        // executes it as NOP.  The executor must mirror that —
        // one Tcy, PC advances by 2, no error.
        let mut core = k20_core_with_flash(&[0xFF, 0xFF]);
        let mut stack = Stack::new();

        let cycles = step(&mut core, &mut stack).expect("NopContinuation is silent NOP");
        assert_eq!(cycles, 1);
        assert_eq!(core.pc(), 0x0002);
    }

    #[test]
    fn step_returns_pc_out_of_bounds_when_word1_unfetchable() {
        // Flash is 0x8000 bytes (0x0000..0x8000).  PC=0x8000 is
        // past the last fetchable byte; word1 cannot be assembled.
        let mut core = Core::new(Variant::Pic18F25K20);
        core.set_pc(0x8000);
        let mut stack = Stack::new();

        let err = step(&mut core, &mut stack).unwrap_err();
        match err {
            ExecError::PcOutOfBounds(pc) => assert_eq!(pc, 0x8000),
            other => panic!("expected PcOutOfBounds, got {other:?}"),
        }
        // PC must NOT have advanced (the executor errors before
        // calling set_pc on the partial-fetch path).
        assert_eq!(core.pc(), 0x8000);
    }

    #[test]
    fn step_succeeds_at_last_word_when_instruction_is_single_word() {
        // PC=0x7FFE with a NOP at the last word: word1 fetchable,
        // word2 not fetchable, but decode returns byte_count=2 so
        // the missing word2 is irrelevant.  Step must succeed.
        let mut core = Core::new(Variant::Pic18F25K20);
        let last_word = 0x8000 - 2;
        core.flash_mut()[last_word] = 0x00; // NOP low byte
        core.flash_mut()[last_word + 1] = 0x00; // NOP high byte
        core.set_pc(last_word as u32);
        let mut stack = Stack::new();

        let cycles = step(&mut core, &mut stack).expect("single-word op at last word OK");
        assert_eq!(cycles, 1);
        // PC wraps via set_pc's mask: 0x7FFE + 2 = 0x8000, masked
        // to 0x001F_FFFE leaves 0x8000 — outside flash on this
        // variant, but `step` did its job.
        assert_eq!(core.pc(), 0x8000);
    }

    #[test]
    fn step_returns_pc_out_of_bounds_on_partial_two_word_fetch() {
        // PC=0x7FFE with the first word of a GOTO at the last
        // word: word1=0xEF00 fetchable, word2 unfetchable.  The
        // decoder needs both words for GOTO; without the executor
        // bailing, it would silently fabricate the continuation
        // from the 0xFFFF sentinel.
        let mut core = Core::new(Variant::Pic18F25K20);
        let last_word = 0x8000 - 2;
        // GOTO 0x0000: word1 = 0xEF00, word2 would be 0xF000.
        core.flash_mut()[last_word] = 0x00; // word1 low (k[7:0])
        core.flash_mut()[last_word + 1] = 0xEF; // word1 high (GOTO opcode)
        core.set_pc(last_word as u32);
        let mut stack = Stack::new();

        let err = step(&mut core, &mut stack).unwrap_err();
        match err {
            ExecError::PcOutOfBounds(pc) => assert_eq!(pc, last_word as u32),
            other => panic!("expected PcOutOfBounds, got {other:?}"),
        }
        // PC must NOT have advanced past the partial fetch.
        assert_eq!(core.pc(), last_word as u32);
    }

    #[test]
    fn step_reports_unimplemented_for_not_yet_wired_instruction() {
        // MOVLW 0x42 — encoding 0x0E42.  Not yet wired into the
        // dispatch in this skeleton commit; future P1.8b commits
        // will land it.  This test pins the Unimplemented arm and
        // will need updating (changed to assert successful exec)
        // when MOVLW lands.
        let mut core = k20_core_with_flash(&[0x42, 0x0E]);
        let mut stack = Stack::new();

        let err = step(&mut core, &mut stack).unwrap_err();
        assert!(
            matches!(err, ExecError::Unimplemented(Instruction::MovLw { k: 0x42 })),
            "expected Unimplemented(MovLw), got {err:?}"
        );
        // PC should still have advanced (the dispatch happens after
        // the fetch+set_pc, so the caller can recover by retrying
        // from a new program counter).
        assert_eq!(core.pc(), 0x0002);
        // Cycle counter stays at 0 — Unimplemented didn't consume
        // a Tcy because no instruction actually ran.
        assert_eq!(core.cycles(), 0);
    }
}
