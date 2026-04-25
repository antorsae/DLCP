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
use crate::isa::{Access, Dest, FsrIndex, Instruction, decode};
use crate::memory::Address;
use crate::stack::Stack;

// ---- Key SFR addresses consulted by the executor ----------------
//
// Every PIC18 SFR is exposed as a byte in the data-memory map at
// `0xF60..=0xFFF`; the executor uses [`Memory::read_raw`] /
// [`Memory::write_raw`] to access them.  Side effects (e.g. INDFn
// indirection, POSTINCn FSR mutation, PCL writes triggering a PC
// update) are NOT modelled in this commit -- they land in the
// FSR-indirect-addressing sub-commit of P1.8b.  The helpers here
// stick to operands that don't trip those special SFRs.

/// `WREG` at 0xFE8.  PIC18's W is exposed as this SFR; reads /
/// writes via the f-operand route through the same byte.
const WREG_ADDR: u16 = 0xFE8;

/// `BSR` at 0xFE0.  Bits 3..0 select the active bank for `a=1`
/// operands; bits 7..4 are unimplemented (read as 0).
const BSR_ADDR: u16 = 0xFE0;

/// `STATUS` at 0xFD8.
const STATUS_ADDR: u16 = 0xFD8;
const STATUS_C: u8 = 0x01;
const STATUS_DC: u8 = 0x02;
const STATUS_Z: u8 = 0x04;
const STATUS_OV: u8 = 0x08;
const STATUS_N: u8 = 0x10;
/// `STATUS` valid bits (bits 5..7 are unimplemented, read as 0).
const STATUS_VALID_MASK: u8 = 0x1F;

// ---- Read/write helpers -----------------------------------------

fn read_w(core: &Core) -> u8 {
    core.memory.read_raw(Address::from_raw(WREG_ADDR))
}

fn write_w(core: &mut Core, value: u8) {
    core.memory.write_raw(Address::from_raw(WREG_ADDR), value);
}

fn read_bsr(core: &Core) -> u8 {
    core.memory.read_raw(Address::from_raw(BSR_ADDR))
}

fn write_bsr(core: &mut Core, value: u8) {
    // Per DS39632E Register 5-2, BSR bits 7..4 are unimplemented.
    core.memory
        .write_raw(Address::from_raw(BSR_ADDR), value & 0x0F);
}

fn read_status(core: &Core) -> u8 {
    core.memory.read_raw(Address::from_raw(STATUS_ADDR))
}

/// Set or clear `mask` bits in STATUS based on `predicate`.  Used
/// by every instruction that touches Z / N / C / DC / OV.
fn set_status_bits(core: &mut Core, mask: u8, predicate: bool) {
    let s = core.memory.read_raw(Address::from_raw(STATUS_ADDR));
    let new = if predicate { s | mask } else { s & !mask };
    core.memory
        .write_raw(Address::from_raw(STATUS_ADDR), new & STATUS_VALID_MASK);
}

/// Set Z and N based on the byte the instruction just produced.
/// Most byte-oriented ops update these two flags; the C/DC/OV
/// updates are op-specific.
fn set_status_zn(core: &mut Core, value: u8) {
    set_status_bits(core, STATUS_Z, value == 0);
    set_status_bits(core, STATUS_N, value & 0x80 != 0);
}

/// Resolve an f-operand into a 12-bit data-memory address using
/// the operand's `a` bit and (for `a=BankSelected`) BSR.
fn resolve_f(core: &Core, f: u8, a: Access) -> Address {
    let bank_selected = matches!(a, Access::BankSelected);
    core.memory.resolve(f, bank_selected, read_bsr(core))
}

fn read_f(core: &Core, f: u8, a: Access) -> u8 {
    core.memory.read_raw(resolve_f(core, f, a))
}

/// Mask away unimplemented bits when writing to an SFR that has
/// some.  Real silicon reads back 0 for those positions
/// regardless of what the firmware wrote (the silicon literally
/// has no storage for them); we apply the mask at write time so
/// `read_raw` returns the silicon-correct value without per-SFR
/// read-side hooks.
///
/// This table covers the *architecturally* documented
/// unimplemented bits per DS39632E Table 5-1 / Register 4-1 /
/// Register 4-2 / §5.4 / §6.3 -- bits whose silicon behaviour is
/// "always read 0" regardless of peripheral configuration.
/// Peripheral SFRs whose bits become inactive only because the
/// peripheral itself is disabled are NOT included; those are
/// modelled by the peripheral wrappers in P2 via
/// `write_byte_through_peripherals`.
const fn sfr_write_mask(addr: u16) -> u8 {
    match addr {
        // STATUS<7:5> unimplemented (Register 5-2).
        STATUS_ADDR => STATUS_VALID_MASK,
        // BSR is a 4-bit register; <7:4> unimplemented (§5.3.2).
        BSR_ADDR => 0x0F,
        // RCON<5> unimplemented (Register 4-1).
        0xFD0 => 0xDF,
        // WDTCON<7:1> unimplemented; only SWDTEN at bit 0 is alive.
        0xFD1 => 0x01,
        // EECON1 bit 5 unimplemented (Register 6-1).
        0xFA6 => 0xDF,
        // EECON2 is not a physical register -- per DS39632E
        // §6.2.1, reads return 0 and writes are consumed by
        // the EE-unlock state machine.  Masking writes to 0x00
        // emulates the read-as-zero contract; the unlock-
        // sequence side effect is the P2 EEPROM peripheral's
        // responsibility.
        0xFA7 => 0x00,
        // FSR0H / FSR1H / FSR2H high nibbles unimplemented
        // (12-bit FSRs; only <3:0> alive in the H register).
        0xFEA | 0xFE2 | 0xFDA => 0x0F,
        // INTCON3 bits 5 and 2 unimplemented (Register 9-3).
        0xFF0 => 0xDB,
        // INTCON2 bits 3 and 1 unimplemented (Register 9-2).
        0xFF1 => 0xF5,
        // TBLPTRU<7:6> unimplemented (TBLPTR is 22 bits; only
        // <5:0> live in TBLPTRU per DS39632E §6.2.3).
        0xFF8 => 0x3F,
        // PCLATU<7:5> unimplemented (PC is 21 bits; only <4:0>
        // alive in PCLATU per DS39632E §5.1.1).
        0xFFB => 0x1F,
        // STKPTR<5> unimplemented (Register 5-1).
        0xFFC => 0xDF,
        // TOSU<7:5> unimplemented (TOS is 21 bits, top 5 bits
        // in TOSU<4:0> per DS39632E §5.1.2.1).
        0xFFF => 0x1F,
        _ => 0xFF,
    }
}

fn write_f(core: &mut Core, f: u8, a: Access, value: u8) {
    let addr = resolve_f(core, f, a);
    write_addr(core, addr, value);
}

/// Write `value` to a 12-bit data-memory address, applying
/// `sfr_write_mask` so unimplemented bits are stripped before
/// the byte lands in the backing array.  Used by MOVFF / LFSR
/// whose operands carry the absolute address directly rather
/// than going through the f-operand resolver.
fn write_addr(core: &mut Core, addr: Address, value: u8) {
    core.memory
        .write_raw(addr, value & sfr_write_mask(addr.as_u16()));
}

/// Write `value` to the destination implied by a byte-oriented
/// op's `d` bit: W (`Dest::W`) or the f-operand (`Dest::F`).
fn write_dest(core: &mut Core, d: Dest, f: u8, a: Access, value: u8) {
    match d {
        Dest::W => write_w(core, value),
        Dest::F => write_f(core, f, a, value),
    }
}

/// Variant of [`write_dest`] for instructions that update STATUS
/// flags as part of their semantics.  Per DS39632E §5.3.6, when
/// STATUS is the destination of a flag-affecting instruction,
/// the result is *not* written -- the flag update from the
/// op's STATUS-bit math is the sole STATUS change that lands.
/// Otherwise the write would clobber the just-set bits.
fn write_dest_preserve_status_flags(
    core: &mut Core,
    d: Dest,
    f: u8,
    a: Access,
    value: u8,
) {
    let target = match d {
        Dest::W => Address::from_raw(WREG_ADDR),
        Dest::F => resolve_f(core, f, a),
    };
    if target.as_u16() == STATUS_ADDR {
        return;
    }
    match d {
        Dest::W => write_w(core, value),
        Dest::F => write_addr(core, target, value),
    }
}

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

/// `true` if `word1` is the first half of one of the four
/// 2-word PIC18 opcodes (MOVFF, CALL, LFSR, GOTO) -- i.e. the
/// instruction needs a real `word2` from flash and the executor
/// must not fall back on the 0xFFFF sentinel.
///
/// Encodings (DS39632E §26):
///   - MOVFF: `1100 ffff ffff ffff`         → word1 high4 = 0xC
///   - CALL : `1110 110s kkkk kkkk`         → word1 high8 ∈ {0xEC, 0xED}
///   - LFSR : `1110 1110 00ff kkkk`, with
///              bits 7..6 = 00 AND
///              bits 5..4 ∈ {00, 01, 10}    → only a *subset* of 0xEE prefixes
///   - GOTO : `1110 1111 kkkk kkkk`         → word1 high8 = 0xEF
///
/// LFSR's stricter shape matters because the decoder rejects
/// invalid `0xEE` prefixes as `Instruction::Reserved` with
/// `byte_count=2` (single-word).  A naive `high8 == 0xEE`
/// predicate would over-match (e.g. `0xEE30`, `0xEE40`,
/// `0xEEFF`) and falsely surface PcOutOfBounds on partial fetch
/// where the correct outcome is "decode as Reserved".
const fn opcode_needs_word2(word1: u16) -> bool {
    let high4 = (word1 >> 12) & 0xF;
    if high4 == 0xC {
        return true;
    }
    let high8 = (word1 >> 8) & 0xFF;
    match high8 {
        0xEC | 0xED | 0xEF => true, // CALL / GOTO -- always 2-word.
        0xEE => {
            // LFSR validity: word1 reserved bits must be clear,
            // and the FSR index field (bits 5..4) must encode
            // FSR0 / FSR1 / FSR2, not the reserved 0b11.
            (word1 & 0x00C0) == 0 && ((word1 >> 4) & 0b11) != 0b11
        }
        _ => false,
    }
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

    // The decoder also wants `word2`.  If it can't be read --
    // we're at the very last word of flash -- and word1 is the
    // first half of a 2-word opcode, refuse to execute: the
    // synthetic sentinel would silently fabricate continuation
    // bits, OR (in LFSR's case) make the decoder return
    // Reserved instead of surfacing the real fetch problem.
    // We use a word1-only predicate because LFSR with an
    // invalid word2 sentinel decodes as Reserved + byte_count=2,
    // so a post-decode `byte_count == 4` check would miss it.
    let word2_available = pc_idx + 3 < flash.len();
    if !word2_available && opcode_needs_word2(word1) {
        return Err(ExecError::PcOutOfBounds(pc));
    }
    let word2 = if word2_available {
        u16::from_le_bytes([flash[pc_idx + 2], flash[pc_idx + 3]])
    } else {
        0xFFFF
    };

    let (instr, byte_count) = decode(word1, word2);
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
        // ---------------- literal / data move (1 Tcy each) -------
        Instruction::MovLw { k } => {
            write_w(core, k);
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::Movwf { a, f } => {
            let w = read_w(core);
            write_f(core, f, a, w);
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::Movf { d, a, f } => {
            // MOVF reads f and writes it to the destination (d).
            // STATUS Z / N reflect the moved byte regardless of d:
            // even `MOVF f, F` (a no-op move) updates the flags --
            // the firmware uses this idiom to test a register
            // without disturbing W.  When d=F and f resolves to
            // STATUS itself, DS39632E §5.3.6 specifies that the
            // result write is dropped so the flag update stands;
            // `write_dest_preserve_status_flags` enforces that.
            let v = read_f(core, f, a);
            set_status_zn(core, v);
            write_dest_preserve_status_flags(core, d, f, a, v);
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::MovLb { k } => {
            // MOVLB loads BSR<3:0> with k<3:0>; bits 7..4 stay 0.
            write_bsr(core, k);
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::Setf { a, f } => {
            // SETF f -- write 0xFF to the f-operand byte.  No
            // STATUS flag updates per DS39632E §26 SETF; if f
            // happens to be STATUS, the unimplemented-bit mask
            // in write_f narrows 0xFF to 0x1F (the implemented
            // bits all get set; bits 7..5 stay 0).
            write_f(core, f, a, 0xFF);
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::Clrf { a, f } => {
            // CLRF f -- clear the f-operand to 0 AND set Z=1.
            // Z is the only flag affected (DS39632E §26).
            // Per §5.3.6, when f=STATUS the result-write of 0
            // would clobber the Z update, so skip the write
            // and let only the flag update land.
            let target = resolve_f(core, f, a);
            if target.as_u16() != STATUS_ADDR {
                write_addr(core, target, 0);
            }
            set_status_bits(core, STATUS_Z, true);
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::Movff { src, dst } => {
            // MOVFF src, dst -- copy one byte between two
            // 12-bit data-memory addresses; 2 Tcy.  No flag
            // updates (DS39632E §26 MOVFF).  Silicon errata
            // notes that dst = PCL / TOSU / TOSH / TOSL is
            // undefined; the simulator just writes through and
            // lets the mask + raw write handle whatever lands.
            let v = core.memory.read_raw(Address::from_raw(src));
            write_addr(core, Address::from_raw(dst), v);
            core.advance_cycles(2);
            Ok(2)
        }
        Instruction::Lfsr { fsr, k } => {
            // LFSR fsr, k (12-bit literal) -- load FSRnH:FSRnL
            // with k.  No flags affected; 2 Tcy.  The high
            // nibble of k is at most 0xF; the FSRnH mask
            // (0x0F) makes the bound explicit at write time.
            let (fsrh, fsrl) = match fsr {
                FsrIndex::Fsr0 => (0xFEAu16, 0xFE9u16),
                FsrIndex::Fsr1 => (0xFE2, 0xFE1),
                FsrIndex::Fsr2 => (0xFDA, 0xFD9),
            };
            write_addr(core, Address::from_raw(fsrh), (k >> 8) as u8);
            write_addr(core, Address::from_raw(fsrl), k as u8);
            core.advance_cycles(2);
            Ok(2)
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
    fn step_returns_pc_out_of_bounds_on_partial_two_word_fetch_goto() {
        // PC=0x7FFE with the first word of a GOTO at the last
        // word: word1=0xEF00 fetchable, word2 unfetchable.  Without
        // the predicate, decode would synthesise word2=0xFFFF and
        // hand back Goto with byte_count=4.
        partial_two_word_fetch_case(&[0x00, 0xEF]);
    }

    #[test]
    fn step_returns_pc_out_of_bounds_on_partial_two_word_fetch_lfsr() {
        // LFSR FSR0, 0: word1=0xEE00, word2=0xF000.  At the last
        // word with word2 unavailable, decode(0xEE00, 0xFFFF)
        // returns *Reserved* (because the sentinel fails LFSR's
        // `word2 & 0xFF00 == 0xF000` check), with byte_count=2 --
        // a post-decode `byte_count == 4` guard would have missed
        // this entirely.
        partial_two_word_fetch_case(&[0x00, 0xEE]);
    }

    #[test]
    fn step_returns_pc_out_of_bounds_on_partial_two_word_fetch_call() {
        // CALL 0, fast=0: word1=0xEC00.
        partial_two_word_fetch_case(&[0x00, 0xEC]);
    }

    #[test]
    fn step_returns_pc_out_of_bounds_on_partial_two_word_fetch_movff() {
        // MOVFF src=0, dst=0: word1=0xC000.
        partial_two_word_fetch_case(&[0x00, 0xC0]);
    }

    fn partial_two_word_fetch_case(word1_bytes: &[u8]) {
        let mut core = Core::new(Variant::Pic18F25K20);
        let last_word = 0x8000 - 2;
        core.flash_mut()[last_word] = word1_bytes[0];
        core.flash_mut()[last_word + 1] = word1_bytes[1];
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
    fn opcode_needs_word2_predicate_matches_documented_two_word_set() {
        // Positive: MOVFF / CALL / valid-LFSR / GOTO prefixes.
        for w in [
            0xC000, 0xCFFF, // MOVFF range (high4 = C)
            0xEC00, 0xED00, // CALL (high8 = EC / ED)
            // LFSR: word1 = 1110 1110 00ff kkkk where ff ∈ {00, 01, 10}.
            0xEE00, // LFSR FSR0, k=0
            0xEE0F, // LFSR FSR0, k[11:8] = 0xF
            0xEE1A, // LFSR FSR1, k[11:8] = 0xA
            0xEE2C, // LFSR FSR2, k[11:8] = 0xC
            0xEF00, 0xEFFF, // GOTO (high8 = EF)
        ] {
            assert!(
                opcode_needs_word2(w),
                "0x{w:04X} should be flagged as 2-word"
            );
        }

        // Negative set, three groups:
        //
        //   1. Genuinely-single-word opcodes that share none of
        //      the predicate's high-bit prefixes.
        //   2. The 0xE8..0xEB unallocated range -- decoder
        //      produces Reserved with byte_count = 2.
        //   3. 0xEE-prefixed words that fail LFSR validity --
        //      the decoder also rejects these as Reserved with
        //      byte_count = 2, so the predicate must mirror.
        for w in [
            // Group 1: single-word ops elsewhere in the ISA.
            0x0000, // NOP
            0x0E42, // MOVLW 0x42
            0xD000, // BRA
            0xD800, // RCALL
            0xE000, 0xE700, // BZ..BNN
            0x6E00, // MOVWF
            0x9000, // BCF
            // Group 2: unallocated 0xE8..0xEB.
            0xE800, 0xEB00,
            // Group 3: 0xEE prefixes the decoder rejects as
            // Reserved.
            0xEE40, // bits 7..6 = 01 (reserved)
            0xEE80, // bits 7..6 = 10 (reserved)
            0xEEC0, // bits 7..6 = 11 (reserved)
            0xEE30, // bits 5..4 = 11 (FSR index = 0b11, invalid)
            0xEEFF, // bits 7..6 = 11 AND ff = 11 (doubly reserved)
        ] {
            assert!(
                !opcode_needs_word2(w),
                "0x{w:04X} should NOT be flagged as 2-word"
            );
        }
    }

    #[test]
    fn step_reports_unimplemented_for_not_yet_wired_instruction() {
        // ADDWF 0x42, W, ACCESS — encoding 0x2442.  Not yet wired
        // into the dispatch (byte-oriented arithmetic lands in a
        // later P1.8b commit).  This test pins the Unimplemented
        // arm and will need updating (changed to assert successful
        // exec) when ADDWF lands.
        let mut core = k20_core_with_flash(&[0x42, 0x24]);
        let mut stack = Stack::new();

        let err = step(&mut core, &mut stack).unwrap_err();
        assert!(
            matches!(err, ExecError::Unimplemented(Instruction::AddWf { .. })),
            "expected Unimplemented(AddWf), got {err:?}"
        );
        // PC should still have advanced (the dispatch happens after
        // the fetch+set_pc, so the caller can recover by retrying
        // from a new program counter).
        assert_eq!(core.pc(), 0x0002);
        // Cycle counter stays at 0 — Unimplemented didn't consume
        // a Tcy because no instruction actually ran.
        assert_eq!(core.cycles(), 0);
    }

    // ------------------------------------------------------------
    // Literal / data-move instructions: MOVLW, MOVWF, MOVF, MOVLB.
    // ------------------------------------------------------------

    #[test]
    fn movlw_loads_literal_into_w() {
        // MOVLW 0x42 — opcode 0x0E42.
        let mut core = k20_core_with_flash(&[0x42, 0x0E]);
        let mut stack = Stack::new();
        let cycles = step(&mut core, &mut stack).unwrap();
        assert_eq!(cycles, 1);
        assert_eq!(read_w(&core), 0x42);
        assert_eq!(core.pc(), 0x0002);
    }

    #[test]
    fn movlw_does_not_touch_status() {
        // MOVLW must not affect Z / N / C / DC / OV.
        let mut core = k20_core_with_flash(&[0x00, 0x0E]); // MOVLW 0x00
        let mut stack = Stack::new();
        // Pre-set every status bit to 1; MOVLW must leave them alone.
        core.memory
            .write_raw(Address::from_raw(STATUS_ADDR), STATUS_VALID_MASK);
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_status(&core), STATUS_VALID_MASK);
        assert_eq!(read_w(&core), 0x00);
    }

    #[test]
    fn movwf_stores_w_into_access_bank_low() {
        // Pre-load: MOVLW 0x55, MOVWF 0x10, ACCESS  (f=0x10 < 0x60 → bank 0 RAM).
        // MOVLW 0x55 = 0x0E55; MOVWF f, ACCESS = 0x6E10 (high8 = 0x6E, low = f).
        let mut core = k20_core_with_flash(&[0x55, 0x0E, 0x10, 0x6E]);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap(); // MOVLW
        step(&mut core, &mut stack).unwrap(); // MOVWF
        // f=0x10 with a=ACCESS lands at bank 0 offset 0x10 → addr 0x010.
        assert_eq!(core.memory.read_raw(Address::from_raw(0x010)), 0x55);
        // W is unchanged.
        assert_eq!(read_w(&core), 0x55);
    }

    #[test]
    fn movwf_stores_w_into_sfr_window_via_access_bank() {
        // f=0x80 with a=ACCESS routes to 0xF80 (Access-Bank high
        // half).  Use 0xC0 → 0xFC0; that's an unused SFR slot on
        // both variants but the executor doesn't know that, just
        // that the byte lands at addr 0xFC0.
        // MOVLW 0xAA = 0x0EAA; MOVWF 0xC0, ACCESS = 0x6EC0.
        let mut core = k20_core_with_flash(&[0xAA, 0x0E, 0xC0, 0x6E]);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFC0)), 0xAA);
    }

    #[test]
    fn movwf_with_bank_selected_uses_bsr() {
        // Set BSR=3; MOVWF 0x40, BANKED → addr (3<<8)|0x40 = 0x340.
        // MOVLW 0x77 = 0x0E77; MOVWF 0x40, BANKED = 0x6F40.
        let mut core = k20_core_with_flash(&[0x77, 0x0E, 0x40, 0x6F]);
        let mut stack = Stack::new();
        write_bsr(&mut core, 3);
        step(&mut core, &mut stack).unwrap(); // MOVLW
        step(&mut core, &mut stack).unwrap(); // MOVWF
        assert_eq!(core.memory.read_raw(Address::from_raw(0x340)), 0x77);
    }

    #[test]
    fn movf_to_w_loads_byte_and_sets_z_when_zero() {
        // RAM[0x10] = 0x00 (default); MOVF 0x10, W, ACCESS = 0x5010.
        let mut core = k20_core_with_flash(&[0x10, 0x50]);
        let mut stack = Stack::new();
        // Pre-clear STATUS so we can see the Z bit appear.
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), 0);
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_w(&core), 0x00);
        assert!(read_status(&core) & STATUS_Z != 0, "Z must be set");
        assert!(read_status(&core) & STATUS_N == 0, "N must be clear");
    }

    #[test]
    fn movf_to_w_sets_n_for_negative_byte() {
        // RAM[0x20] = 0x80 → bit 7 set → N=1.
        // MOVF 0x20, W, ACCESS = 0x5020.
        let mut core = k20_core_with_flash(&[0x20, 0x50]);
        core.memory.write_raw(Address::from_raw(0x020), 0x80);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_w(&core), 0x80);
        assert!(read_status(&core) & STATUS_N != 0, "N must be set");
        assert!(read_status(&core) & STATUS_Z == 0, "Z must be clear");
    }

    #[test]
    fn movf_to_w_with_nonzero_positive_clears_z_and_n() {
        // RAM[0x30] = 0x42; MOVF 0x30, W, ACCESS = 0x5030.
        let mut core = k20_core_with_flash(&[0x30, 0x50]);
        core.memory.write_raw(Address::from_raw(0x030), 0x42);
        // Pre-set Z + N so we can confirm they get cleared.
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), STATUS_Z | STATUS_N);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_w(&core), 0x42);
        assert!(read_status(&core) & STATUS_Z == 0);
        assert!(read_status(&core) & STATUS_N == 0);
    }

    #[test]
    fn movf_to_f_writes_back_and_still_updates_status() {
        // The "MOVF f, F" idiom is firmware shorthand for "test
        // f without disturbing W".  The byte lands back in f and
        // STATUS Z / N reflect it; W stays whatever it was.
        // MOVF 0x10, F, ACCESS = 0x5210 (d=F has bit 9 set).
        let mut core = k20_core_with_flash(&[0x10, 0x52]);
        core.memory.write_raw(Address::from_raw(0x010), 0x00);
        write_w(&mut core, 0xFF); // marker: must remain 0xFF.
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), 0);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0x010)), 0x00);
        assert_eq!(read_w(&core), 0xFF, "W must be untouched by MOVF f, F");
        assert!(read_status(&core) & STATUS_Z != 0);
    }

    // ------------------------------------------------------------
    // SETF / CLRF / MOVFF / LFSR -- complete the data-movement
    // category.
    // ------------------------------------------------------------

    #[test]
    fn setf_writes_all_ones_to_access_bank_low_register() {
        // SETF f, a=ACCESS: encoding 0110 1000 ffff ffff = 0x68ff.
        // f=0x10 → Access-Bank low → addr 0x010.
        let mut core = k20_core_with_flash(&[0x10, 0x68]);
        let mut stack = Stack::new();
        let cycles = step(&mut core, &mut stack).unwrap();
        assert_eq!(cycles, 1);
        assert_eq!(core.memory.read_raw(Address::from_raw(0x010)), 0xFF);
    }

    #[test]
    fn setf_to_status_lands_only_implemented_bits() {
        // SETF STATUS, ACCESS: f=0xD8 → 0xFD8.  STATUS_VALID_MASK
        // narrows the 0xFF write to 0x1F.  SETF doesn't touch
        // flags itself, so the result IS the new STATUS.
        let mut core = k20_core_with_flash(&[0xD8, 0x68]);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_status(&core), STATUS_VALID_MASK);
    }

    #[test]
    fn clrf_writes_zero_and_sets_z() {
        // CLRF f, a=ACCESS: encoding 0110 1010 ffff ffff = 0x6Aff.
        // f=0x20 → addr 0x020.  Pre-load 0xAA so we see it clear.
        let mut core = k20_core_with_flash(&[0x20, 0x6A]);
        core.memory.write_raw(Address::from_raw(0x020), 0xAA);
        // Pre-clear STATUS so we see Z appear.
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), 0);
        let mut stack = Stack::new();
        let cycles = step(&mut core, &mut stack).unwrap();
        assert_eq!(cycles, 1);
        assert_eq!(core.memory.read_raw(Address::from_raw(0x020)), 0x00);
        assert!(read_status(&core) & STATUS_Z != 0, "Z must be set");
    }

    #[test]
    fn clrf_to_status_preserves_other_flags_and_sets_z() {
        // Per DS39632E §5.3.6: a flag-affecting op targeting
        // STATUS drops the result write -- only the flag
        // update lands.  CLRF only affects Z, so C/DC/OV/N
        // must survive a `CLRF STATUS, ACCESS`.
        // f=0xD8 → STATUS at 0xFD8.  Encoding 0x6AD8.
        let mut core = k20_core_with_flash(&[0xD8, 0x6A]);
        // Pre-set every implemented STATUS bit; CLRF should
        // leave C/DC/OV/N alone and Z stays set (was already 1).
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), STATUS_VALID_MASK);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        // C, DC, OV, N must survive; Z stays set.
        assert!(read_status(&core) & STATUS_C != 0);
        assert!(read_status(&core) & STATUS_DC != 0);
        assert!(read_status(&core) & STATUS_OV != 0);
        assert!(read_status(&core) & STATUS_N != 0);
        assert!(read_status(&core) & STATUS_Z != 0);
    }

    #[test]
    fn movff_copies_byte_between_arbitrary_data_memory_addresses() {
        // MOVFF 0x123, 0x456 -- 2-word encoding:
        //   word1 = 1100 ffff ffff ffff = 0xC123
        //   word2 = 1111 ffff ffff ffff = 0xF456
        let mut core = k20_core_with_flash(&[0x23, 0xC1, 0x56, 0xF4]);
        // Source byte at 0x123 (bank 1 offset 0x23).
        core.memory.write_raw(Address::from_raw(0x123), 0xA5);
        let mut stack = Stack::new();
        let cycles = step(&mut core, &mut stack).unwrap();
        assert_eq!(cycles, 2, "MOVFF costs 2 Tcy (2-word op)");
        assert_eq!(core.pc(), 0x0004, "PC advances by 4 bytes");
        // Source unchanged, destination has the copy.
        assert_eq!(core.memory.read_raw(Address::from_raw(0x123)), 0xA5);
        assert_eq!(core.memory.read_raw(Address::from_raw(0x456)), 0xA5);
    }

    #[test]
    fn movff_to_sfr_with_unimplemented_bits_applies_mask() {
        // MOVFF 0x100 → STATUS (0xFD8): if source byte has
        // bits 7..5 set, the SFR mask must strip them so STATUS
        // only retains bits 4..0.
        // word1 = 0xC100 (src=0x100), word2 = 0xFFD8 (dst=0xFD8;
        // upper nibble of word2 is don't-care, decoder takes only
        // the low 12 bits).
        let mut core = k20_core_with_flash(&[0x00, 0xC1, 0xD8, 0xFF]);
        core.memory.write_raw(Address::from_raw(0x100), 0xFF);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_status(&core), STATUS_VALID_MASK);
    }

    #[test]
    fn lfsr_loads_12_bit_literal_into_fsr0() {
        // LFSR FSR0, 0x123 -- 2-word encoding:
        //   word1 = 1110 1110 00ff kkkk where ff=0 (FSR0), k[11:8]=0x1
        //         = 1110 1110 0000 0001 = 0xEE01
        //   word2 = 1111 0000 kkkk kkkk where k[7:0]=0x23
        //         = 1111 0000 0010 0011 = 0xF023
        let mut core = k20_core_with_flash(&[0x01, 0xEE, 0x23, 0xF0]);
        let mut stack = Stack::new();
        let cycles = step(&mut core, &mut stack).unwrap();
        assert_eq!(cycles, 2, "LFSR costs 2 Tcy (2-word op)");
        assert_eq!(core.pc(), 0x0004);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFE9)), 0x23);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFEA)), 0x01);
    }

    #[test]
    fn lfsr_loads_into_fsr1_and_fsr2() {
        // LFSR FSR1, 0x4AB and LFSR FSR2, 0x7DE in sequence.
        let mut core = k20_core_with_flash(&[
            // LFSR FSR1, 0x4AB:
            //   word1 = 0xEE14 (ff=01=FSR1, k[11:8]=4)
            //   word2 = 0xF0AB (k[7:0]=AB)
            0x14, 0xEE, 0xAB, 0xF0,
            // LFSR FSR2, 0x7DE:
            //   word1 = 0xEE27 (ff=10=FSR2, k[11:8]=7)
            //   word2 = 0xF0DE (k[7:0]=DE)
            0x27, 0xEE, 0xDE, 0xF0,
        ]);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFE1)), 0xAB);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFE2)), 0x04);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFD9)), 0xDE);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFDA)), 0x07);
    }

    #[test]
    fn movlb_writes_low_4_bits_of_bsr() {
        // MOVLB 0x05 — opcode 0x0105 (per decoder; high8=0x01).
        let mut core = k20_core_with_flash(&[0x05, 0x01]);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_bsr(&core), 0x05);
    }

    #[test]
    fn movf_status_to_status_preserves_flag_update() {
        // DS39632E §5.3.6: when STATUS is the destination of a
        // flag-affecting instruction, the result write is
        // dropped; only the flag update lands.  `MOVF STATUS, F`
        // with STATUS initially 0 must end with Z set, NOT with
        // STATUS still equal to its original 0.
        //
        // STATUS in access-bank low: f = STATUS_ADDR & 0xFF = 0xD8.
        // MOVF 0xD8, F, ACCESS = 0x52D8.
        let mut core = k20_core_with_flash(&[0xD8, 0x52]);
        // Pre-clear STATUS.
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), 0);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        // Without the fix: STATUS would be re-written as 0,
        // clobbering the Z-set step.  With the fix: Z stays set.
        assert!(read_status(&core) & STATUS_Z != 0, "Z must survive");
    }

    #[test]
    fn movf_status_to_w_loads_status_byte_normally() {
        // When d=W, the result write goes to W (not STATUS), so
        // the flag update + the W load both happen.
        let mut core = k20_core_with_flash(&[0xD8, 0x50]); // MOVF 0xD8, W, ACCESS
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), STATUS_C); // C set
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        // W picks up the original STATUS byte (only C set).
        assert_eq!(read_w(&core), STATUS_C);
        // STATUS gets Z/N updated based on the loaded byte (0x01):
        // not zero, bit 7 clear → Z=0, N=0.  C bit was already
        // set on entry; Z/N updates leave C alone.
        assert!(read_status(&core) & STATUS_Z == 0);
        assert!(read_status(&core) & STATUS_N == 0);
        assert!(read_status(&core) & STATUS_C != 0, "C must remain set");
    }

    #[test]
    fn movwf_to_status_strips_unimplemented_bits() {
        // STATUS<7:5> are unimplemented (read as 0 on real
        // silicon).  A MOVWF STATUS attempt with W=0xFF must
        // store only STATUS_VALID_MASK = 0x1F.
        // MOVLW 0xFF = 0x0EFF; MOVWF 0xD8, ACCESS = 0x6ED8.
        let mut core = k20_core_with_flash(&[0xFF, 0x0E, 0xD8, 0x6E]);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap(); // MOVLW
        step(&mut core, &mut stack).unwrap(); // MOVWF
        assert_eq!(
            read_status(&core),
            STATUS_VALID_MASK,
            "STATUS<7:5> must read as 0 even after a 0xFF write"
        );
    }

    #[test]
    fn movwf_to_bsr_strips_unimplemented_bits() {
        // BSR<7:4> are unimplemented.  MOVWF BSR with W=0xF7
        // must store only the low nibble.
        // MOVLW 0xF7 = 0x0EF7; MOVWF 0xE0, ACCESS = 0x6EE0.
        let mut core = k20_core_with_flash(&[0xF7, 0x0E, 0xE0, 0x6E]);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_bsr(&core), 0x07);
    }

    #[test]
    fn movwf_to_intcon2_strips_unimplemented_bits() {
        // INTCON2<3,1> unimplemented (Register 9-2).  MOVWF
        // INTCON2 with W=0xFF must store 0xF5.
        // MOVLW 0xFF = 0x0EFF; MOVWF 0xF1, ACCESS = 0x6EF1.
        let mut core = k20_core_with_flash(&[0xFF, 0x0E, 0xF1, 0x6E]);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFF1)), 0xF5);
    }

    #[test]
    fn movwf_to_eecon1_strips_unimplemented_bit_5() {
        // EECON1<5> unimplemented (Register 6-1).  EECON1 is
        // at 0xFA6 (gputils p18f2455.inc); 0xA6 is in the
        // Access-Bank high half so a=ACCESS routes there.
        // MOVLW 0xFF = 0x0EFF; MOVWF 0xA6, ACCESS = 0x6EA6.
        let mut core = k20_core_with_flash(&[0xFF, 0x0E, 0xA6, 0x6E]);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFA6)), 0xDF);
    }

    #[test]
    fn movwf_to_eecon2_zeroes_storage() {
        // EECON2 is not a physical register; reads return 0
        // (DS39632E §6.2.1).  Mask writes to 0x00 so a later
        // raw read (or MOVF) returns the silicon-correct 0,
        // not whatever the firmware wrote.
        // EECON2 at 0xFA7; f=0xA7 routes via Access-Bank high.
        // MOVLW 0xFF = 0x0EFF; MOVWF 0xA7, ACCESS = 0x6EA7.
        let mut core = k20_core_with_flash(&[0xFF, 0x0E, 0xA7, 0x6E]);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFA7)), 0x00);
    }

    #[test]
    fn movwf_to_intcon3_strips_unimplemented_bits() {
        // INTCON3<5,2> unimplemented (Register 9-3).
        // MOVWF 0xF0, ACCESS = 0x6EF0.
        let mut core = k20_core_with_flash(&[0xFF, 0x0E, 0xF0, 0x6E]);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFF0)), 0xDB);
    }

    #[test]
    fn movwf_to_fsr0h_strips_high_nibble() {
        // FSR0H<7:4> unimplemented (12-bit FSR; only <3:0>
        // alive).  MOVWF FSR0H with W=0xCB must store only
        // 0x0B.  This is the most user-visible case of the
        // sfr_write_mask extension -- firmware sets up indirect
        // pointers via MOVWF FSR0H and read-back must match
        // silicon's 0-read-for-unimplemented contract.
        // MOVLW 0xCB = 0x0ECB; MOVWF 0xEA, ACCESS = 0x6EEA.
        let mut core = k20_core_with_flash(&[0xCB, 0x0E, 0xEA, 0x6E]);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFEA)), 0x0B);
    }

    #[test]
    fn movlb_truncates_literal_to_4_bits() {
        // PIC18 BSR is 4 bits; MOVLB stores the low nibble only.
        // The decoder pulls only the low 4 bits of the literal
        // from word1 (`word1 & 0x0F`), so an attempt to encode
        // `MOVLB 0xFA` actually decodes as MOVLB 0x0A.  The
        // executor's BSR write also masks to 4 bits as a
        // belt-and-suspenders guard.  Pin both layers by
        // pre-setting BSR to 0xFF (raw) and confirming the high
        // nibble gets cleared after MOVLB.
        // Build opcode by hand: word1 = 0x010A → MOVLB 0x0A.
        let mut core = k20_core_with_flash(&[0x0A, 0x01]);
        // Stash garbage in the BSR high nibble by writing raw.
        core.memory.write_raw(Address::from_raw(BSR_ADDR), 0xF7);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_bsr(&core), 0x0A);
    }
}
