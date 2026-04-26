//! USB-SIE peripheral — Phase-2 stub.
//!
//! ## Scope
//!
//! 2455-only.  The CONTROL K20 has no USB peripheral, so
//! the variant gate makes this a no-op there.
//!
//! ## What this is NOT (Phase-2 deferral)
//!
//! Real V3.2 / V2.x firmware uses the USB-SIE for the HFD
//! host's HID interface: cmd 0x20 (preset switch), 0x21
//! (diagnostic query), 0x43 (memory-read), 0x44 (Tier-1
//! diag snapshot), plus filename A/B routing for the DSP
//! upload.  Implementing the full HID dispatch path
//! requires endpoint state machines, BD-table management,
//! and SETUP / IN / OUT transfer flow tracking -- a
//! substantial peripheral that's intentionally deferred to
//! the V3.2 MAIN parity gate work that actually exercises
//! it.
//!
//! ## What this IS (Phase-2 ship)
//!
//! - The `Usb` struct with the standard
//!   `{new, reset_state, on_sfr_write, tick_tcy}` surface.
//! - Variant-gated logic that no-ops on K20.
//! - A parity-test entry point that asserts the wiring
//!   (peripheral instance exists; reset doesn't crash;
//!   tick_tcy doesn't crash).
//!
//! V1.71 cycle-10 boot doesn't touch USB so no behavioural
//! regression risk for the existing parity tests.

use crate::memory::{Memory, Variant};

#[derive(Clone, Debug, Default)]
pub struct Usb {
    is_2455: bool,
}

impl Usb {
    pub fn new(variant: Variant) -> Self {
        Usb {
            is_2455: matches!(variant, Variant::Pic18F2455),
        }
    }

    pub fn reset_state(&mut self) {
        // Nothing to reset in Phase-2; stub.
    }

    pub fn on_sfr_write(&mut self, _addr: u16, _value: u8, _mem: &mut Memory) {
        if !self.is_2455 {
            return;
        }
        // Phase-2 stub: no USB SFRs are tracked yet.  The
        // V3.2 MAIN parity gate work will fill in handlers
        // for UCON, UEPx, UADDR, USTAT, etc. as the HID
        // dispatch state machine lands.
    }

    pub fn tick_tcy(&mut self, _n: u32, _mem: &mut Memory) {
        if !self.is_2455 {
            return;
        }
        // Phase-2 stub: no time-driven USB state to advance.
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn k20_construction_marks_non_2455() {
        let usb = Usb::new(Variant::Pic18F25K20);
        assert!(!usb.is_2455);
    }

    #[test]
    fn pic2455_construction_marks_2455() {
        let usb = Usb::new(Variant::Pic18F2455);
        assert!(usb.is_2455);
    }

    #[test]
    fn reset_state_is_a_noop_in_phase_2() {
        let mut usb = Usb::new(Variant::Pic18F2455);
        usb.reset_state();
        // Just ensure no panic.
    }

    #[test]
    fn tick_tcy_is_a_noop_in_phase_2() {
        let mut usb = Usb::new(Variant::Pic18F2455);
        let mut mem = Memory::new(Variant::Pic18F2455);
        usb.tick_tcy(1_000_000, &mut mem);
        // No panic.
    }
}
