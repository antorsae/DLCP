//! P2.9 Oscillator subsystem parity gate.
//!
//! Phase-2 oscillator is SFR-semantic only.  Tests:
//!   1. universal-clock conversion factor per variant
//!      matches the spec's 48 MHz LCM derivation.
//!   2. OSCCON / RCON.IPEN POR values from the K20_POR
//!      table land correctly through apply_reset.
//!   3. Phase-3 work (HFINTOSC settle, PLL ENABLE/READY,
//!      SCS dynamic switching) is documented as deferred
//!      and does not block the cycle-10 V1.71 parity test.

use dlcp_sim::core::Core;
use dlcp_sim::memory::{Address, Variant};
use dlcp_sim::peripherals::osc::ticks_per_tcy;
use dlcp_sim::reset::{ResetSource, apply_reset};
use dlcp_sim::stack::Stack;

const OSCCON_ADDR: u16 = 0xFD3;
const RCON_ADDR: u16 = 0xFD0;

#[test]
fn k20_universal_factor_is_16() {
    assert_eq!(ticks_per_tcy(Variant::Pic18F25K20), 16);
}

#[test]
fn pic2455_universal_factor_is_12() {
    assert_eq!(ticks_per_tcy(Variant::Pic18F2455), 12);
}

#[test]
fn k20_osccon_por_value_from_k20_por_table() {
    let mut core = Core::new(Variant::Pic18F25K20);
    let mut stack = Stack::new();
    apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
    // K20_POR sets OSCCON = 0x30 (DS Tbl 4-4 base
    // `0011 qq00`; the GPSIM_K20_DEVIATIONS table in the
    // V1.71 parity test exempts the gpsim-side 0x40
    // base-class initial value).
    assert_eq!(core.memory.read_raw(Address::from_raw(OSCCON_ADDR)), 0x30);
}

#[test]
fn rcon_por_value_includes_ri_to_pd() {
    // Per Tbl 4-4 RCON `0q-1 11q0`: RI=1 (bit 4), TO=1 (bit
    // 3), PD=1 (bit 2) at POR.  apply_reset's POR arm
    // composes RCON_RI | RCON_TO | RCON_PD = 0x1C and writes
    // it to memory after the SFR-window pass.
    let mut core = Core::new(Variant::Pic18F25K20);
    let mut stack = Stack::new();
    apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
    let rcon = core.memory.read_raw(Address::from_raw(RCON_ADDR));
    assert_eq!(rcon, 0x1C);
}

#[test]
fn por_does_not_panic_on_either_variant() {
    let mut k20 = Core::new(Variant::Pic18F25K20);
    let mut s = Stack::new();
    apply_reset(&mut k20, &mut s, ResetSource::PowerOn);
    let mut p2455 = Core::new(Variant::Pic18F2455);
    let mut s2 = Stack::new();
    apply_reset(&mut p2455, &mut s2, ResetSource::PowerOn);
}
