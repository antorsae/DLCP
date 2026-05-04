//! PIC18 FSR indirect-addressing modes.
//!
//! Each PIC18 has three 12-bit indirect-pointer registers
//! (FSR0, FSR1, FSR2) and four "virtual" file-register addresses
//! per FSR that the silicon decodes as an indirect read/write at
//! the pointer (with optional post/pre modify), plus PLUSWn which
//! adds a signed copy of W.  In a byte-oriented instruction
//! these addresses look like ordinary `f` operands, but the
//! actual memory access goes through `FSRn` instead of falling
//! into bank 15.
//!
//! Reference: DS39632E §5.5.4 + Tables 5-1/5-2 (PIC18F2455 SFR
//! map) and DS41303G §5.5.4 (PIC18F25K20 — same encoding).
//! Confirmed against gputils' `p18f2455.inc` for the
//! `INDFn / POSTINCn / POSTDECn / PREINCn / PLUSWn` addresses.
//!
//! ## Address map
//!
//! ```text
//! FSR0:  PLUSW0  PREINC0  POSTDEC0  POSTINC0  INDF0
//!        0xFEB   0xFEC    0xFED     0xFEE     0xFEF
//!
//! FSR1:  PLUSW1  PREINC1  POSTDEC1  POSTINC1  INDF1
//!        0xFE3   0xFE4    0xFE5     0xFE6     0xFE7
//!
//! FSR2:  PLUSW2  PREINC2  POSTDEC2  POSTINC2  INDF2
//!        0xFDB   0xFDC    0xFDD     0xFDE     0xFDF
//! ```
//!
//! All 15 indirect-access addresses are inside the
//! top-of-bank-15 SFR window (`addr >= 0xF60`), so the executor
//! checks `Address::is_sfr()` first and only consults
//! [`classify_fsr_indirect`] within that window.
//!
//! P1.4 lays down the addressing classifier and its tests.  The
//! interpreter (P1.5+) consumes the result: it reads/writes the
//! FSR pair (FSRnH:FSRnL) to compute the actual data-memory
//! address, applies the post/pre-modify, and (for PLUSWn)
//! sign-extends W before the add.

#![allow(dead_code, reason = "P1.4 classifier; consumed by P1.5+ interpreter")]

use crate::isa::decode::FsrIndex;
use serde::{Deserialize, Serialize};

/// Indirect-access mode encoded in the file-register address.
#[derive(Serialize, Deserialize, Copy, Clone, Eq, PartialEq, Debug, Hash)]
pub enum FsrAccessMode {
    /// `INDFn` — read/write `*FSRn`; FSR is left untouched.
    Indirect,
    /// `POSTINCn` — read/write `*FSRn`, then `FSRn += 1`.
    PostIncrement,
    /// `POSTDECn` — read/write `*FSRn`, then `FSRn -= 1`.
    PostDecrement,
    /// `PREINCn` — `FSRn += 1`, then read/write `*FSRn`.
    PreIncrement,
    /// `PLUSWn` — read/write `*(FSRn + (signed)W)`; FSRn and W
    /// are both untouched.  W is interpreted as a signed `i8`
    /// (range `-128..=+127`) per DS39632E §26.
    PlusW,
}

/// Classify a 12-bit file-register address as an FSR
/// indirect-access slot.
///
/// Returns `None` if `addr` is not one of the 15 special FSR
/// addresses (i.e., the operand should be resolved as a normal
/// SFR or RAM byte).  The address is matched against the full
/// 12-bit value, not the 8-bit `f` field, so callers that have
/// only the operand can pass `Address::from_raw(0xF00 | f).as_u16()`
/// for an `a=0, f>=0x60` access — this matches what
/// [`crate::memory::Memory::resolve`] returns.
///
/// Note: the executor in P1.5+ should call this AFTER
/// [`crate::memory::Memory::resolve`] has produced an
/// [`crate::memory::Address`], and only when that address has
/// `is_sfr() == true`.  Calling it for non-SFR addresses returns
/// `None` (correct, but wasted work).
pub const fn classify_fsr_indirect(addr: u16) -> Option<(FsrIndex, FsrAccessMode)> {
    match addr {
        // FSR0 block: 0xFEB..=0xFEF
        0xFEB => Some((FsrIndex::Fsr0, FsrAccessMode::PlusW)),
        0xFEC => Some((FsrIndex::Fsr0, FsrAccessMode::PreIncrement)),
        0xFED => Some((FsrIndex::Fsr0, FsrAccessMode::PostDecrement)),
        0xFEE => Some((FsrIndex::Fsr0, FsrAccessMode::PostIncrement)),
        0xFEF => Some((FsrIndex::Fsr0, FsrAccessMode::Indirect)),
        // FSR1 block: 0xFE3..=0xFE7
        0xFE3 => Some((FsrIndex::Fsr1, FsrAccessMode::PlusW)),
        0xFE4 => Some((FsrIndex::Fsr1, FsrAccessMode::PreIncrement)),
        0xFE5 => Some((FsrIndex::Fsr1, FsrAccessMode::PostDecrement)),
        0xFE6 => Some((FsrIndex::Fsr1, FsrAccessMode::PostIncrement)),
        0xFE7 => Some((FsrIndex::Fsr1, FsrAccessMode::Indirect)),
        // FSR2 block: 0xFDB..=0xFDF
        0xFDB => Some((FsrIndex::Fsr2, FsrAccessMode::PlusW)),
        0xFDC => Some((FsrIndex::Fsr2, FsrAccessMode::PreIncrement)),
        0xFDD => Some((FsrIndex::Fsr2, FsrAccessMode::PostDecrement)),
        0xFDE => Some((FsrIndex::Fsr2, FsrAccessMode::PostIncrement)),
        0xFDF => Some((FsrIndex::Fsr2, FsrAccessMode::Indirect)),
        _ => None,
    }
}

/// Hardware addresses of the FSR low byte for each FSR index.
/// Used by the interpreter (P1.5+) to read/write the pointer.
///
/// FSR0L=0xFE9, FSR1L=0xFE1, FSR2L=0xFD9 per DS39632E Table 5-1
/// (data rows; cross-checked against gputils `p18f2455.inc`).
pub const fn fsr_low_addr(fsr: FsrIndex) -> u16 {
    match fsr {
        FsrIndex::Fsr0 => 0xFE9,
        FsrIndex::Fsr1 => 0xFE1,
        FsrIndex::Fsr2 => 0xFD9,
    }
}

/// Hardware addresses of the FSR high byte (the upper 4 bits of
/// the 12-bit pointer; the high 4 bits of FSRnH are unimplemented
/// and read as 0 per DS39632E §5.5.4).
pub const fn fsr_high_addr(fsr: FsrIndex) -> u16 {
    match fsr {
        FsrIndex::Fsr0 => 0xFEA,
        FsrIndex::Fsr1 => 0xFE2,
        FsrIndex::Fsr2 => 0xFDA,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // ----- Coverage: every documented FSR slot maps to its (fsr, mode) pair -----

    #[test]
    fn indf0_maps_to_fsr0_indirect() {
        assert_eq!(
            classify_fsr_indirect(0xFEF),
            Some((FsrIndex::Fsr0, FsrAccessMode::Indirect)),
        );
    }

    #[test]
    fn postinc0_maps_to_fsr0_post_increment() {
        assert_eq!(
            classify_fsr_indirect(0xFEE),
            Some((FsrIndex::Fsr0, FsrAccessMode::PostIncrement)),
        );
    }

    #[test]
    fn postdec0_maps_to_fsr0_post_decrement() {
        assert_eq!(
            classify_fsr_indirect(0xFED),
            Some((FsrIndex::Fsr0, FsrAccessMode::PostDecrement)),
        );
    }

    #[test]
    fn preinc0_maps_to_fsr0_pre_increment() {
        assert_eq!(
            classify_fsr_indirect(0xFEC),
            Some((FsrIndex::Fsr0, FsrAccessMode::PreIncrement)),
        );
    }

    #[test]
    fn plusw0_maps_to_fsr0_plus_w() {
        assert_eq!(
            classify_fsr_indirect(0xFEB),
            Some((FsrIndex::Fsr0, FsrAccessMode::PlusW)),
        );
    }

    #[test]
    fn indf1_maps_to_fsr1_indirect() {
        assert_eq!(
            classify_fsr_indirect(0xFE7),
            Some((FsrIndex::Fsr1, FsrAccessMode::Indirect)),
        );
    }

    #[test]
    fn postinc1_maps_to_fsr1_post_increment() {
        assert_eq!(
            classify_fsr_indirect(0xFE6),
            Some((FsrIndex::Fsr1, FsrAccessMode::PostIncrement)),
        );
    }

    #[test]
    fn postdec1_maps_to_fsr1_post_decrement() {
        assert_eq!(
            classify_fsr_indirect(0xFE5),
            Some((FsrIndex::Fsr1, FsrAccessMode::PostDecrement)),
        );
    }

    #[test]
    fn preinc1_maps_to_fsr1_pre_increment() {
        assert_eq!(
            classify_fsr_indirect(0xFE4),
            Some((FsrIndex::Fsr1, FsrAccessMode::PreIncrement)),
        );
    }

    #[test]
    fn plusw1_maps_to_fsr1_plus_w() {
        assert_eq!(
            classify_fsr_indirect(0xFE3),
            Some((FsrIndex::Fsr1, FsrAccessMode::PlusW)),
        );
    }

    #[test]
    fn indf2_maps_to_fsr2_indirect() {
        assert_eq!(
            classify_fsr_indirect(0xFDF),
            Some((FsrIndex::Fsr2, FsrAccessMode::Indirect)),
        );
    }

    #[test]
    fn postinc2_maps_to_fsr2_post_increment() {
        assert_eq!(
            classify_fsr_indirect(0xFDE),
            Some((FsrIndex::Fsr2, FsrAccessMode::PostIncrement)),
        );
    }

    #[test]
    fn postdec2_maps_to_fsr2_post_decrement() {
        assert_eq!(
            classify_fsr_indirect(0xFDD),
            Some((FsrIndex::Fsr2, FsrAccessMode::PostDecrement)),
        );
    }

    #[test]
    fn preinc2_maps_to_fsr2_pre_increment() {
        assert_eq!(
            classify_fsr_indirect(0xFDC),
            Some((FsrIndex::Fsr2, FsrAccessMode::PreIncrement)),
        );
    }

    #[test]
    fn plusw2_maps_to_fsr2_plus_w() {
        assert_eq!(
            classify_fsr_indirect(0xFDB),
            Some((FsrIndex::Fsr2, FsrAccessMode::PlusW)),
        );
    }

    // ----- Negative cases: addresses that look adjacent but are NOT FSR slots -----

    #[test]
    fn fsr_low_high_addresses_are_not_indirect() {
        // FSR0L = 0xFE9, FSR0H = 0xFEA — these are the regular
        // SFRs that hold the pointer itself; reading them does
        // NOT trigger an indirect access.
        assert_eq!(classify_fsr_indirect(0xFE9), None); // FSR0L
        assert_eq!(classify_fsr_indirect(0xFEA), None); // FSR0H
        assert_eq!(classify_fsr_indirect(0xFE1), None); // FSR1L
        assert_eq!(classify_fsr_indirect(0xFE2), None); // FSR1H
        assert_eq!(classify_fsr_indirect(0xFD9), None); // FSR2L
        assert_eq!(classify_fsr_indirect(0xFDA), None); // FSR2H
    }

    #[test]
    fn wreg_is_not_indirect() {
        // WREG = 0xFE8 — sits exactly between the FSR0 and FSR1
        // blocks but is not an indirect slot.
        assert_eq!(classify_fsr_indirect(0xFE8), None);
    }

    #[test]
    fn ram_addresses_below_sfr_window_are_not_indirect() {
        for &addr in &[0x000, 0x05F, 0x100, 0x4FE, 0xF5F] {
            assert_eq!(
                classify_fsr_indirect(addr),
                None,
                "addr=0x{:03X} should not classify as FSR indirect",
                addr,
            );
        }
    }

    #[test]
    fn other_sfr_addresses_are_not_indirect() {
        // BAUDCON = 0xFB8, STATUS = 0xFD8, BSR = 0xFE0, PCL =
        // 0xFF9, etc.  None of these are FSR indirect slots.
        for &addr in &[0xFB8, 0xFD8, 0xFE0, 0xFF9, 0xFF0, 0xFCF, 0xFC0, 0xFFF] {
            assert_eq!(
                classify_fsr_indirect(addr),
                None,
                "addr=0x{:03X} should not classify as FSR indirect",
                addr,
            );
        }
    }

    // ----- FSR low / high SFR addresses match documented map -----

    #[test]
    fn fsr_low_addresses_match_datasheet() {
        assert_eq!(fsr_low_addr(FsrIndex::Fsr0), 0xFE9);
        assert_eq!(fsr_low_addr(FsrIndex::Fsr1), 0xFE1);
        assert_eq!(fsr_low_addr(FsrIndex::Fsr2), 0xFD9);
    }

    #[test]
    fn fsr_high_addresses_match_datasheet() {
        assert_eq!(fsr_high_addr(FsrIndex::Fsr0), 0xFEA);
        assert_eq!(fsr_high_addr(FsrIndex::Fsr1), 0xFE2);
        assert_eq!(fsr_high_addr(FsrIndex::Fsr2), 0xFDA);
    }

    // ----- Coverage roll-call: exactly 15 indirect slots -----

    #[test]
    fn exactly_15_fsr_indirect_slots() {
        // PIC18 architecture defines exactly 5 modes × 3 FSRs =
        // 15 special file-register addresses.  This test will
        // fail if classify_fsr_indirect ever grows extra arms
        // (or loses one).
        let mut count = 0;
        for addr in 0u16..=0xFFF {
            if classify_fsr_indirect(addr).is_some() {
                count += 1;
            }
        }
        assert_eq!(count, 15);
    }
}
