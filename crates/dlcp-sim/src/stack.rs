//! PIC18 hardware return-address stack.
//!
//! 31 21-bit slots, separately stored from data memory and not
//! addressable as banked RAM.  CALL / RCALL / interrupts push;
//! RETURN / RETFIE pop; the top three slots are also exposed
//! through TOSU/TOSH/TOSL for software inspection.  The stack
//! pointer (STKPTR) is an SFR at 0xFFC whose low 5 bits are the
//! depth (`0..=31`) and whose top two bits latch overflow
//! (STKFUL, bit 7) and underflow (STKUNF, bit 6) — both sticky
//! until the user clears them.
//!
//! Reference: DS39632E §5.4 (Stack and Stack-related Registers,
//! pp. 71-74) and DS41303G §5.4 (PIC18F25K20 — same encoding).
//! Both variants share the 31-deep architectural depth.
//!
//! ## STVREN config bit (out-of-scope here)
//!
//! The stack module reports overflow / underflow events via
//! [`Stack::overflow`] / [`Stack::underflow`].  Whether those
//! events trigger a reset is governed by the **STVREN** bit in
//! `CONFIG4L` (DS39632E §22.1) — that decision is made by the
//! reset-source dispatcher (P1.6) after consulting the parsed
//! configuration words (P1.7).  P1.5's job is to make the
//! architectural state visible; resetting on overflow is a
//! policy that lives outside this module.

#![allow(dead_code, reason = "P1.5 storage; consumed by P1.6 reset path + P1.2 CALL/RETURN executor")]

use crate::core::Core;

/// Maximum number of return addresses the PIC18 hardware stack
/// can hold.
pub const STACK_DEPTH: usize = 31;

/// `STKPTR` SFR address on both PIC18 variants.
pub const STKPTR_ADDR: u16 = 0xFFC;

/// `TOSL` SFR address.  Reads/writes the low byte of the
/// top-of-stack slot.
pub const TOSL_ADDR: u16 = 0xFFD;

/// `TOSH` SFR address.  Reads/writes the high byte.
pub const TOSH_ADDR: u16 = 0xFFE;

/// `TOSU` SFR address.  Reads/writes the upper byte (low 5 bits
/// only; the top 3 bits are unimplemented and read as 0 per
/// DS39632E §5.4).
pub const TOSU_ADDR: u16 = 0xFFF;

/// Mask for the low 5-bit pointer field of STKPTR.
pub const STKPTR_INDEX_MASK: u8 = 0x1F;

/// `STKUNF` (Stack Underflow Flag), STKPTR bit 6.  Sticky.
pub const STKPTR_STKUNF: u8 = 0x40;

/// `STKFUL` (Stack Full Flag), STKPTR bit 7.  Sticky.
pub const STKPTR_STKFUL: u8 = 0x80;

/// One return-address stack frame.
///
/// PIC18 stack slots are 21 bits wide (the same width as PC).
/// Internally we store them as `u32` and mask to 21 bits on
/// every write so a caller that hands us a value with high
/// bits set (e.g. via `Core::pc()`-derived arithmetic) can't
/// corrupt the slot.  Bit 0 of the stored value is masked off
/// the same way [`Core::set_pc`] enforces (PCL[0] is hard-
/// wired to 0).
#[derive(Copy, Clone, Eq, PartialEq, Debug, Default, Hash)]
pub struct StackEntry(u32);

impl StackEntry {
    pub const fn from_pc(pc: u32) -> Self {
        StackEntry(pc & 0x001F_FFFE)
    }

    pub const fn as_pc(self) -> u32 {
        self.0
    }
}

/// PIC18 hardware return-address stack with the architectural
/// 31-deep depth and STKPTR sticky flags.
///
/// `Default` initialises the stack to its POR state: all 31
/// slots zeroed, STKPTR=0 (empty), no overflow / underflow
/// flagged.
#[derive(Clone)]
pub struct Stack {
    /// Backing array.  Index `i` (0..=30) is the slot loaded
    /// when the pointer reaches `i+1`.
    slots: [StackEntry; STACK_DEPTH],
    /// Number of slots currently in use (0..=31).  STKFUL is set
    /// BY the push that fills the 31st slot (i.e. the
    /// transition `depth: 30 -> 31`), not by the next attempted
    /// push — see `Stack::push` for the matching DS39632E §5.4.2
    /// citation.  At `depth == STACK_DEPTH` further pushes are
    /// silently dropped and STKFUL stays asserted.
    depth: u8,
    /// Sticky overflow / underflow latch (STKPTR bits 6..7).
    flags: u8,
}

impl Default for Stack {
    fn default() -> Self {
        Stack {
            slots: [StackEntry::default(); STACK_DEPTH],
            depth: 0,
            flags: 0,
        }
    }
}

impl Stack {
    /// Construct an empty stack.  Equivalent to `Stack::default()`.
    pub fn new() -> Self {
        Self::default()
    }

    /// Reset to POR: all 31 slots zeroed, depth = 0, flags
    /// cleared.  Invoked on POR / BOR; *not* on
    /// MCLR / WDT / RESET-instruction (those preserve the stack
    /// per DS39632E Table 4-1, p. 53).
    pub fn por_reset(&mut self) {
        *self = Self::default();
    }

    /// Number of frames currently in use (0..=31).
    pub const fn depth(&self) -> u8 {
        self.depth
    }

    /// True if STKFUL has been latched since the last clear.
    /// STKFUL fires in two cases (DS39632E §5.4.2):
    ///
    /// 1. The push that fills the 31st slot (depth: 30 → 31).
    ///    Sets STKFUL even though the push was accepted.
    /// 2. A push attempted at depth==31 (overflow).  The push
    ///    is dropped and STKFUL stays asserted.
    ///
    /// Mirrored into STKPTR.STKFUL on every read.  Cleared by
    /// software writing 0 to that bit (via `write_stkptr` or
    /// `clear_flags`); never set by software.
    pub const fn overflow(&self) -> bool {
        (self.flags & STKPTR_STKFUL) != 0
    }

    /// True if RETURN / RETFIE / POP was issued on an empty
    /// stack since the last clear.  Mirrored into STKPTR.STKUNF.
    pub const fn underflow(&self) -> bool {
        (self.flags & STKPTR_STKUNF) != 0
    }

    /// Clear both overflow and underflow latches.  The user
    /// firmware does this by writing zeros to STKPTR.STKFUL /
    /// STKPTR.STKUNF; we expose it as a method so the SFR-write
    /// hook can call it without poking internal state.
    pub fn clear_flags(&mut self) {
        self.flags = 0;
    }

    /// Reset the pointer to 0 while latching `STKFUL`.  Called
    /// by [`crate::reset::apply_reset`] when a Stack-Full reset
    /// fires (DS39632E §5.4.2: "The STKFUL bit will remain set
    /// and the Stack Pointer will be set to zero").  The slot
    /// data is preserved — the spec does NOT clear the stored
    /// return addresses on a Stack-Full reset.
    pub fn reset_for_stack_full(&mut self) {
        self.depth = 0;
        self.flags |= STKPTR_STKFUL;
    }

    /// Reset the pointer to 0 while latching `STKUNF`.  Called
    /// when a Stack-Underflow reset fires; pointer was already
    /// at 0 in that case but we re-assert it for clarity.  Slot
    /// data preserved (no stored addresses to clear at depth=0
    /// anyway).
    pub fn reset_for_stack_underflow(&mut self) {
        self.depth = 0;
        self.flags |= STKPTR_STKUNF;
    }

    /// Push a return address.  Per DS39632E §5.4.2:
    ///
    ///   "After the PC is pushed onto the stack 31 times
    ///    (without popping any values off the stack), the
    ///    STKFUL bit is set... If STVREN is set, the 31st push
    ///    will push the (PC + 2) value onto the stack, set the
    ///    STKFUL bit and reset the device."
    ///
    /// In other words, STKFUL is set BY the push that fills
    /// the last slot — not by the next attempted push.  The
    /// caller (P1.6 reset dispatcher) sees `overflow() == true`
    /// after a push returns `true`-but-just-filled and consults
    /// STVREN to decide whether to reset.  A subsequent push at
    /// depth=31 is silently dropped (datasheet: "Any additional
    /// pushes will not overwrite the 31st push and the STKPTR
    /// will remain at 31") and re-asserts STKFUL so a software-
    /// cleared latch is re-set on the next overflow attempt.
    ///
    /// Return value: `true` if the address was stored,
    /// `false` if the push was dropped due to a full stack.
    pub fn push(&mut self, pc: u32) -> bool {
        if (self.depth as usize) >= STACK_DEPTH {
            // Stack was already full before this push.  Drop
            // the address and re-assert STKFUL — protects
            // against software clearing the latch and then
            // attempting another push.
            self.flags |= STKPTR_STKFUL;
            return false;
        }
        self.slots[self.depth as usize] = StackEntry::from_pc(pc);
        self.depth += 1;
        if (self.depth as usize) >= STACK_DEPTH {
            // The push that just filled the 31st slot sets
            // STKFUL on real silicon (DS39632E §5.4.2).
            self.flags |= STKPTR_STKFUL;
        }
        true
    }

    /// Pop a return address.  Returns `Some(pc)` if a value was
    /// available; returns `None` and sets STKUNF otherwise.
    /// Per DS39632E §5.4 the underflow-pop returns 0x000000.
    pub fn pop(&mut self) -> Option<u32> {
        if self.depth == 0 {
            self.flags |= STKPTR_STKUNF;
            return None;
        }
        self.depth -= 1;
        Some(self.slots[self.depth as usize].as_pc())
    }

    /// Peek the top of stack without modifying state.  Returns
    /// 0 when the stack is empty; matches the silicon behaviour
    /// of TOSU/TOSH/TOSL reading 0 at depth=0.
    pub const fn top(&self) -> u32 {
        if self.depth == 0 {
            0
        } else {
            self.slots[(self.depth - 1) as usize].as_pc()
        }
    }

    /// Set the top of stack (TOSU/TOSH/TOSL software writes).
    /// At depth=0 the write is silently dropped — matches
    /// silicon behaviour (the TOSU/TOSH/TOSL bytes still
    /// read 0 in that state).
    pub fn set_top(&mut self, pc: u32) {
        if self.depth > 0 {
            self.slots[(self.depth - 1) as usize] = StackEntry::from_pc(pc);
        }
    }

    /// Compose the STKPTR SFR byte from the current state.
    pub const fn stkptr(&self) -> u8 {
        (self.flags & (STKPTR_STKFUL | STKPTR_STKUNF))
            | (self.depth & STKPTR_INDEX_MASK)
    }

    /// Apply a software write to STKPTR.  Bits 4..0 set the new
    /// depth (clamped to 31 since 5 bits already encode
    /// 0..=31).  Bits 6..7 are read-and-clear-only flags: a
    /// write of 0 to STKFUL/STKUNF clears that latch; a write
    /// of 1 has no effect (matches silicon).
    pub fn write_stkptr(&mut self, value: u8) {
        let new_depth = value & STKPTR_INDEX_MASK;
        self.depth = new_depth;
        // Clearing flags: software-written 0 in either flag
        // bit clears the corresponding latch.  Per DS39632E
        // §5.4.2, the flags are NOT settable by software (you
        // can't mark the stack as full just by writing 1).
        let mask = STKPTR_STKFUL | STKPTR_STKUNF;
        self.flags &= value & mask;
    }
}

/// Read TOSU/TOSH/TOSL slices for the SFR-read hook.
///
/// PIC18 exposes the top of stack as three 8-bit reads (low,
/// high, upper).  The mapping:
///
///   TOSL = top &  0xFF
///   TOSH = (top >> 8)  & 0xFF
///   TOSU = (top >> 16) & 0x1F   (high 3 bits read 0)
pub const fn tos_byte(stack: &Stack, addr: u16) -> u8 {
    let top = stack.top();
    match addr {
        TOSL_ADDR => (top & 0xFF) as u8,
        TOSH_ADDR => ((top >> 8) & 0xFF) as u8,
        TOSU_ADDR => ((top >> 16) & 0x1F) as u8,
        _ => 0,
    }
}

/// Apply an SFR write to TOSU/TOSH/TOSL by patching the
/// corresponding byte of the current top-of-stack value, then
/// writing it back via [`Stack::set_top`].  Out-of-range `addr`
/// is a no-op.
pub fn write_tos_byte(stack: &mut Stack, addr: u16, value: u8) {
    let top = stack.top();
    let new_top = match addr {
        TOSL_ADDR => (top & 0x001F_FF00) | (value as u32),
        TOSH_ADDR => (top & 0x001F_00FF) | ((value as u32) << 8),
        TOSU_ADDR => (top & 0x0000_FFFF) | (((value as u32) & 0x1F) << 16),
        _ => return,
    };
    stack.set_top(new_top);
}

// Stub link to Core (Stack will be embedded there in P1.6).
const _: fn() = || {
    let _: Option<&Core> = None;
};

#[cfg(test)]
mod tests {
    use super::*;

    // ----- POR / empty-state semantics -----

    #[test]
    fn por_state_is_empty() {
        let s = Stack::new();
        assert_eq!(s.depth(), 0);
        assert_eq!(s.stkptr(), 0);
        assert_eq!(s.top(), 0);
        assert!(!s.overflow());
        assert!(!s.underflow());
    }

    #[test]
    fn por_reset_clears_everything() {
        let mut s = Stack::new();
        for i in 0..STACK_DEPTH {
            s.push((i as u32) * 4);
        }
        assert_eq!(s.depth(), 31);
        s.por_reset();
        assert_eq!(s.depth(), 0);
        assert_eq!(s.top(), 0);
        assert!(!s.overflow());
        assert!(!s.underflow());
    }

    // ----- Push / pop happy path -----

    #[test]
    fn push_then_pop_returns_lifo() {
        let mut s = Stack::new();
        assert!(s.push(0x4576));
        assert!(s.push(0x4FE0));
        assert!(s.push(0x1000));
        assert_eq!(s.depth(), 3);
        assert_eq!(s.pop(), Some(0x1000));
        assert_eq!(s.pop(), Some(0x4FE0));
        assert_eq!(s.pop(), Some(0x4576));
        assert_eq!(s.depth(), 0);
    }

    #[test]
    fn push_masks_pc_to_21_bits_and_clears_lsb() {
        // Stored PC must respect the same invariant as
        // Core::set_pc: 21-bit width AND bit 0 cleared.
        let mut s = Stack::new();
        s.push(0xFFFF_FFFF);
        assert_eq!(s.top(), 0x001F_FFFE);
        s.por_reset();
        s.push(0x4577); // odd value
        assert_eq!(s.top(), 0x4576);
    }

    // ----- Overflow -----

    #[test]
    fn pushing_30_does_not_set_stkful() {
        // Per DS39632E §5.4.2 STKFUL is set BY the 31st push;
        // pushes 1..=30 leave the latch clear.
        let mut s = Stack::new();
        for i in 0..30 {
            assert!(s.push((i as u32) * 4));
        }
        assert_eq!(s.depth(), 30);
        assert!(!s.overflow());
    }

    #[test]
    fn the_31st_push_sets_stkful_immediately() {
        // Datasheet quote: "the 31st push will push the (PC + 2)
        // value onto the stack, set the STKFUL bit and reset the
        // device" (with STVREN=1; reset is P1.6's call).  The
        // stack module just sets the flag on the push that
        // fills the last slot.
        let mut s = Stack::new();
        for i in 0..30 {
            s.push((i as u32) * 4);
        }
        assert!(!s.overflow());
        // 31st push:
        assert!(s.push(0xCAFE));
        assert_eq!(s.depth(), 31);
        assert!(s.overflow());
    }

    #[test]
    fn push_at_full_stack_is_dropped_and_keeps_stkful() {
        // Datasheet (STVREN=0 path): "Any additional pushes
        // will not overwrite the 31st push and the STKPTR will
        // remain at 31".
        let mut s = Stack::new();
        for i in 0..STACK_DEPTH {
            s.push((i as u32) * 4);
        }
        assert!(s.overflow());
        let top_before = s.top();
        // 32nd push: dropped, depth stays at 31, top unchanged.
        assert!(!s.push(0xDEAD));
        assert_eq!(s.depth(), 31);
        assert_eq!(s.top(), top_before);
        assert!(s.overflow());
    }

    #[test]
    fn push_at_full_re_asserts_stkful_after_software_clear() {
        // Defensive: if firmware clears STKFUL while still at
        // depth=31 and then tries another push, the latch
        // should reassert.
        let mut s = Stack::new();
        for i in 0..STACK_DEPTH {
            s.push((i as u32) * 4);
        }
        s.clear_flags();
        assert!(!s.overflow());
        s.push(0xDEAD); // dropped, but flag re-asserted
        assert!(s.overflow());
    }

    #[test]
    fn push_at_full_via_write_stkptr_software_clear_drops_push() {
        // The same scenario as above but going through the
        // write_stkptr SFR path that real firmware uses to
        // clear STKFUL: write the depth field plus zero in
        // bits 6..7.
        let mut s = Stack::new();
        for i in 0..STACK_DEPTH {
            s.push((i as u32) * 4);
        }
        // write_stkptr(0x1F) preserves depth=31 but clears the
        // sticky flags by AND'ing with `value & 0xC0` = 0.
        s.write_stkptr(0x1F);
        assert_eq!(s.depth(), 31);
        assert!(!s.overflow());
        // Next push is dropped and re-asserts STKFUL.
        let top_before = s.top();
        let accepted = s.push(0xDEAD);
        assert!(!accepted);
        assert_eq!(s.depth(), 31);
        assert_eq!(s.top(), top_before);
        assert!(s.overflow());
    }

    #[test]
    fn pop_then_push_reuses_top_slot_and_returns_true() {
        // After STKFUL is set by the 31st push, pop one frame.
        // depth = 30, STKFUL stays set (sticky).  The next push
        // must succeed (returns true) and refill the 31st
        // slot, re-asserting STKFUL through the same code path.
        let mut s = Stack::new();
        for i in 0..STACK_DEPTH {
            s.push(0x0010 + i as u32);
        }
        assert!(s.overflow());
        // Pop the top frame.
        let popped = s.pop();
        assert_eq!(popped, Some(0x0010 + (STACK_DEPTH as u32) - 1));
        assert_eq!(s.depth(), 30);
        // Push a new frame: should be accepted, slot 30 reused,
        // depth back to 31, STKFUL still asserted.
        assert!(s.push(0xCAFE));
        assert_eq!(s.depth(), 31);
        assert_eq!(s.top(), 0xCAFE);
        assert!(s.overflow());
    }

    #[test]
    fn overflow_flag_is_sticky() {
        let mut s = Stack::new();
        for _ in 0..STACK_DEPTH {
            s.push(0);
        }
        // STKFUL is already set by the 31st push.
        assert!(s.overflow());
        // Pop one frame — STKFUL stays set (it's sticky).
        s.pop();
        assert!(s.overflow());
        // Until cleared explicitly.
        s.clear_flags();
        assert!(!s.overflow());
    }

    // ----- Underflow -----

    #[test]
    fn pop_on_empty_returns_none_and_sets_underflow() {
        let mut s = Stack::new();
        assert_eq!(s.pop(), None);
        assert!(s.underflow());
    }

    #[test]
    fn underflow_flag_is_sticky() {
        let mut s = Stack::new();
        s.pop();
        assert!(s.underflow());
        // Push something — STKUNF stays set until cleared
        s.push(0x1000);
        assert!(s.underflow());
        s.clear_flags();
        assert!(!s.underflow());
    }

    // ----- TOS register interface -----

    #[test]
    fn tos_bytes_match_top() {
        let mut s = Stack::new();
        s.push(0x0014_5678);
        assert_eq!(tos_byte(&s, TOSL_ADDR), 0x78);
        assert_eq!(tos_byte(&s, TOSH_ADDR), 0x56);
        assert_eq!(tos_byte(&s, TOSU_ADDR), 0x14);
    }

    #[test]
    fn tos_upper_byte_is_clipped_to_5_bits() {
        let mut s = Stack::new();
        // Stored top is masked to 21 bits, so even pushing
        // 0xFFFF_FFFF leaves only 0x1F in the upper byte.
        s.push(0xFFFF_FFFF);
        assert_eq!(tos_byte(&s, TOSU_ADDR), 0x1F);
    }

    #[test]
    fn write_tos_byte_patches_correct_slice() {
        let mut s = Stack::new();
        s.push(0x0000_0000);
        write_tos_byte(&mut s, TOSL_ADDR, 0x42);
        assert_eq!(s.top(), 0x0000_0042);
        write_tos_byte(&mut s, TOSH_ADDR, 0xAB);
        assert_eq!(s.top(), 0x0000_AB42);
        write_tos_byte(&mut s, TOSU_ADDR, 0x05);
        assert_eq!(s.top(), 0x0005_AB42);
    }

    #[test]
    fn write_tos_byte_clears_lsb_via_set_top_invariant() {
        let mut s = Stack::new();
        s.push(0x0000_0000);
        // Set TOSL to an odd value via the SFR path; the
        // set_top invariant should drop the LSB.
        write_tos_byte(&mut s, TOSL_ADDR, 0x77);
        assert_eq!(s.top(), 0x0000_0076);
    }

    #[test]
    fn write_tos_byte_at_depth_zero_is_silent() {
        let mut s = Stack::new();
        write_tos_byte(&mut s, TOSL_ADDR, 0xFF);
        assert_eq!(s.top(), 0);
    }

    // ----- STKPTR composition / decomposition -----

    #[test]
    fn stkptr_composes_index_and_flags() {
        let mut s = Stack::new();
        for _ in 0..3 {
            s.push(0);
        }
        assert_eq!(s.stkptr(), 3);
        // Force overflow + underflow to be set sticky.
        for _ in 0..(STACK_DEPTH + 1) {
            s.push(0);
        }
        // Now depth = 31, STKFUL = 1.
        assert_eq!(s.stkptr() & STKPTR_STKFUL, STKPTR_STKFUL);
        assert_eq!(s.stkptr() & STKPTR_INDEX_MASK, 31);
    }

    #[test]
    fn write_stkptr_clears_flags_via_zero_write() {
        let mut s = Stack::new();
        // Force both flags set.
        for _ in 0..(STACK_DEPTH + 1) {
            s.push(0);
        }
        s.pop(); // depth back to 30, STKFUL still sticky
        let before = s.stkptr();
        assert_eq!(before & STKPTR_STKFUL, STKPTR_STKFUL);
        // Write 0x00: index bits to 0, both flags get the
        // AND with their respective mask bits in `value` —
        // both 0 → cleared.
        s.write_stkptr(0);
        assert_eq!(s.stkptr(), 0);
        assert!(!s.overflow());
        assert!(!s.underflow());
    }

    #[test]
    fn write_stkptr_cannot_set_flags_by_writing_one() {
        // Per DS39632E §5.4.2: STKFUL and STKUNF cannot be
        // *set* by software, only cleared.  Writing 1 to those
        // bits when the latch is already 0 must leave the
        // latch at 0.
        let mut s = Stack::new();
        s.write_stkptr(STKPTR_STKFUL | STKPTR_STKUNF);
        assert!(!s.overflow());
        assert!(!s.underflow());
    }

    #[test]
    fn write_stkptr_low_5_bits_are_the_depth() {
        let mut s = Stack::new();
        s.write_stkptr(0x05);
        assert_eq!(s.depth(), 5);
        s.write_stkptr(0x1F);
        assert_eq!(s.depth(), 31);
    }

    #[test]
    fn write_stkptr_ignores_unimplemented_bit_5() {
        // Bit 5 is unimplemented per DS39632E §5.4.2 — writes
        // are ignored.  Our mask is 0x1F (bits 4..0), so
        // bit 5 falls through cleanly.
        let mut s = Stack::new();
        s.write_stkptr(0x20 | 0x05); // bit 5 set, depth=5
        assert_eq!(s.depth(), 5);
    }
}
