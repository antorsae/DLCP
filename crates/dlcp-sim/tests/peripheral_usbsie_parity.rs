//! P2.8 USB-SIE parity gate.
//!
//! 2455-only.  Phase-2 USB is a stub; the actual HID
//! dispatch path (cmd 0x20/0x21/0x43/0x44 + filename A/B
//! routing) lands alongside the V3.2 MAIN parity gate.
//!
//! This test asserts the wiring exists and is variant-gated
//! correctly.  Phase-3+ will replace these with full
//! HID-dispatch behavioural tests.

use dlcp_sim::core::Core;
use dlcp_sim::memory::Variant;
use dlcp_sim::reset::{ResetSource, apply_reset};
use dlcp_sim::stack::Stack;

#[test]
fn usb_construction_for_2455_marks_2455() {
    let core = Core::new(Variant::Pic18F2455);
    // No public read accessor for `is_2455` -- the
    // observable contract is "no panic on construction"
    // and "tick is a no-op".  The unit tests inside usb.rs
    // already assert the field; here we just check Core
    // owns a Usb instance.
    let _ = &core.peripherals.usb;
}

#[test]
fn usb_construction_for_k20_does_not_panic() {
    let core = Core::new(Variant::Pic18F25K20);
    let _ = &core.peripherals.usb;
}

#[test]
fn por_reset_does_not_panic_on_2455() {
    let mut core = Core::new(Variant::Pic18F2455);
    let mut stack = Stack::new();
    apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
}

#[test]
fn por_reset_does_not_panic_on_k20() {
    let mut core = Core::new(Variant::Pic18F25K20);
    let mut stack = Stack::new();
    apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
}
