//! Single PIC18 core: program memory, data memory, ALU registers,
//! and the cycle counter.  P1.1 only lays the storage; the
//! instruction interpreter (P1.2-P1.4), hardware stack (P1.5),
//! reset path (P1.6), and config-bit parser (P1.7) wire behaviour
//! into this struct.
//!
//! ## What lives here vs. elsewhere
//!
//! * `Core` owns the bytes — flash, RAM, ALU regs, cycle counter.
//! * The ALU registers (`W`, `STATUS`, `BSR`, `FSRn`, `STKPTR`,
//!   `PCL/PCH/PCLATH/PCLATU`) are PIC18 SFRs in real silicon, so
//!   they live inside the [`crate::memory::Memory`] backing array
//!   too — but the interpreter accesses them through dedicated
//!   helpers since they're touched on every instruction.  P1.2
//!   adds those helpers; P1.1 just allocates the storage.
//! * Peripheral side-effects on SFR writes (BAUDCON.BRG16
//!   reconfiguring the baud generator, EECON1.WR triggering an
//!   EEPROM write, etc.) live in `crate::peripherals::*` from P2
//!   onward.  `Core` is unaware of them; the dispatcher in P2
//!   wraps `Memory::write_raw` to fan out to peripherals.
//!
//! ## Cycle counter semantics
//!
//! `cycles` counts **instruction cycles** (Tcy), not the universal
//! 48 MHz tick that the multi-core scheduler uses in P3.  A core
//! running at 16 MHz Fosc has Tcy = 250 ns and increments `cycles`
//! by 1 per single-Tcy instruction (most ops), 2 per multi-Tcy
//! instruction (CALL, GOTO, table read, etc.).  P3's `Chain`
//! converts Tcy → universal ticks via `ticks_per_tcy`.

#![allow(dead_code, reason = "P1.1 skeleton; behaviour wired in P1.2+")]

use crate::memory::{Memory, Variant};

/// Default reset vector for both supported PIC18 variants.
/// Confirmed to be 0x0000 in DS39632E §5.2 and DS41303G §5.2
/// (PIC18 ISA architectural constant, same for every PIC18 chip).
pub const RESET_VECTOR: u32 = 0x0000;

/// One PIC18 core: program memory + data memory + cycle counter.
/// P1.1 only allocates storage.  Reset, instruction fetch, decode,
/// and execute all come online in subsequent sub-tasks; this
/// struct carries the state they will mutate.
#[derive(Clone)]
pub struct Core {
    variant: Variant,
    /// Program memory (flash).  Byte-addressed; PIC18 instructions
    /// are 16-bit (2 bytes) at even addresses, but the storage
    /// itself is per-byte so the table-read instructions work
    /// uniformly.  Sized via [`Variant::program_memory_bytes`].
    flash: Box<[u8]>,
    /// Data memory: banked RAM + SFR window.  See [`Memory`].
    pub memory: Memory,
    /// Program counter.  PIC18 PC is 21 bits (the upper byte
    /// `PCLATU` is only 5 bits wide) AND byte-addressed but
    /// architecturally word-aligned: PCL bit 0 is hard-wired to
    /// 0 in silicon (DS39632E §5.5.1, DS41303G §5.5.1).  We
    /// widen to `u32` for arithmetic convenience and rely on
    /// [`Core::set_pc`] to keep `pc & !0x001F_FFFE == 0` —
    /// upper 11 bits clear AND bit 0 clear — at all times.
    pc: u32,
    /// Total Tcy elapsed since the last reset.  Plain `u64` is
    /// enough for >250 years at 4 MIPS, far beyond any test run.
    cycles: u64,
}

impl Core {
    /// Construct an empty core with `flash` and `memory` zero-
    /// filled.  The caller (P1.7's hex loader and P1.6's reset
    /// path) is responsible for populating flash from a hex file
    /// and bringing SFRs to their POR values before instruction
    /// fetch begins.
    pub fn new(variant: Variant) -> Self {
        let flash = vec![0u8; variant.program_memory_bytes()].into_boxed_slice();
        let memory = Memory::new(variant);
        Core {
            variant,
            flash,
            memory,
            pc: RESET_VECTOR,
            cycles: 0,
        }
    }

    /// Variant this core was constructed for.
    pub const fn variant(&self) -> Variant {
        self.variant
    }

    /// Borrow the program-memory bytes (read-only).  The hex
    /// loader (P1.7) writes through [`Self::flash_mut`].
    pub fn flash(&self) -> &[u8] {
        &self.flash
    }

    /// Mutable borrow of the program-memory bytes.  Used by the
    /// hex loader and by the table-write instructions
    /// (`TBLWT*`) which can self-program flash on PIC18.
    pub fn flash_mut(&mut self) -> &mut [u8] {
        &mut self.flash
    }

    /// Read the program counter.
    pub const fn pc(&self) -> u32 {
        self.pc
    }

    /// Set the program counter.  Reset and the GOTO/CALL/RETURN
    /// family of instructions go through here; raw assignment
    /// during state restore (P5.1 snapshot/restore) too.
    ///
    /// The PIC18 PC is 21 bits AND byte-addressed but always
    /// instruction-aligned: PCL bit 0 is hard-wired to 0 in
    /// silicon (DS39632E §5.5.1, DS41303G §5.5.1) so instruction
    /// fetch never sees an odd PC.  Mask both the upper bits
    /// (above bit 20) and bit 0 to enforce that invariant here;
    /// a caller that hands us an odd value (`pc | 1`) loses
    /// only the always-zero LSB.
    pub fn set_pc(&mut self, pc: u32) {
        self.pc = pc & 0x001F_FFFE;
    }

    /// Total instruction cycles elapsed since the last reset.
    pub const fn cycles(&self) -> u64 {
        self.cycles
    }

    /// Advance the cycle counter by `n` Tcy.  Called by the
    /// instruction interpreter (P1.2) once per instruction.
    pub fn advance_cycles(&mut self, n: u32) {
        self.cycles = self.cycles.saturating_add(n as u64);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn new_core_is_zero_filled() {
        let core = Core::new(Variant::Pic18F25K20);
        assert_eq!(core.pc(), RESET_VECTOR);
        assert_eq!(core.cycles(), 0);
        assert!(core.flash().iter().all(|&b| b == 0));
        assert!(core.memory.as_slice().iter().all(|&b| b == 0));
    }

    #[test]
    fn flash_size_matches_variant() {
        // Both variants currently allocate full 32 KiB; see
        // `Variant::program_memory_bytes` for rationale.
        assert_eq!(Core::new(Variant::Pic18F25K20).flash().len(), 32 * 1024);
        assert_eq!(Core::new(Variant::Pic18F2455).flash().len(), 32 * 1024);
    }

    #[test]
    fn data_memory_size_matches_variant() {
        assert_eq!(Core::new(Variant::Pic18F25K20).memory.as_slice().len(), 4096);
        assert_eq!(Core::new(Variant::Pic18F2455).memory.as_slice().len(), 4096);
    }

    #[test]
    fn pc_is_masked_to_21_bits_and_word_aligned() {
        let mut core = Core::new(Variant::Pic18F2455);
        // 0xFFFF_FFFF asks for "all bits set"; we expect both the
        // upper-11-bits clear AND bit 0 clear (PCL[0] is hard-
        // wired to 0 on PIC18).  Result: 0x001F_FFFE, the largest
        // architecturally legal PC value.
        core.set_pc(0xFFFF_FFFF);
        assert_eq!(core.pc(), 0x001F_FFFE);
    }

    #[test]
    fn pc_set_drops_odd_lsb() {
        // A caller handing us PC|1 (e.g., from a buggy table
        // read or a state restore that lost alignment) should
        // see the LSB silently cleared, not a stored odd value.
        let mut core = Core::new(Variant::Pic18F2455);
        core.set_pc(0x4577);
        assert_eq!(core.pc(), 0x4576);
    }

    #[test]
    fn advance_cycles_accumulates() {
        let mut core = Core::new(Variant::Pic18F25K20);
        core.advance_cycles(1);
        core.advance_cycles(2);
        assert_eq!(core.cycles(), 3);
    }

    #[test]
    fn advance_cycles_saturates_at_u64_max() {
        let mut core = Core::new(Variant::Pic18F25K20);
        core.cycles = u64::MAX - 1;
        core.advance_cycles(10);
        assert_eq!(core.cycles(), u64::MAX);
    }
}
