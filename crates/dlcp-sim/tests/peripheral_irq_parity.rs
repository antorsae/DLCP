//! P2.7 IRQ controller parity gate.
//!
//! Phase-2 IRQ is a query surface only -- the executor does
//! not yet vector to 0x0008 / 0x0018 on a pending IRQ.  These
//! tests assert the SFR semantics + `is_irq_pending` priority
//! decisions for the documented PIE/PIR/GIE/IPEN combos.

use dlcp_sim::core::Core;
use dlcp_sim::exec::step;
use dlcp_sim::memory::{Address, Variant};
use dlcp_sim::peripherals::irq::{
    INTCON_ADDR, IPR1_ADDR, PIE1_ADDR, PIR1_ADDR, RCON_ADDR, is_irq_pending,
    is_irq_pending_high, is_irq_pending_low,
};
use dlcp_sim::reset::{ResetSource, apply_reset};
use dlcp_sim::stack::Stack;

const INTCON_GIE: u8 = 1 << 7;
const INTCON_PEIE: u8 = 1 << 6;
const RCON_IPEN: u8 = 1 << 7;

fn encode_movlw(k: u8) -> [u8; 2] {
    [k, 0x0E]
}
fn encode_movwf(f: u8) -> [u8; 2] {
    let word = 0x6E00u16 | (f as u16);
    [word as u8, (word >> 8) as u8]
}

/// Build a flash that:
///   1. Enables RCON.IPEN
///   2. Enables INTCON.GIE | PEIE
///   3. Loops on BRA -1
fn build_irq_demo_flash() -> Vec<u8> {
    let mut flash = vec![0u8; 32 * 1024];
    let prog: &[(u32, [u8; 2])] = &[
        (0x0000, encode_movlw(RCON_IPEN)),
        (0x0002, encode_movwf(0xD0)), // RCON @ 0xFD0
        (0x0004, encode_movlw(INTCON_GIE | INTCON_PEIE)),
        (0x0006, encode_movwf(0xF2)), // INTCON @ 0xFF2
        (0x0008, [0xFF, 0xD7]),       // BRA -1
    ];
    for (a, bytes) in prog {
        flash[*a as usize] = bytes[0];
        flash[*a as usize + 1] = bytes[1];
    }
    flash
}

fn run_demo(cycle_target: u64) -> Core {
    let mut core = Core::new(Variant::Pic18F25K20);
    core.flash_mut().copy_from_slice(&build_irq_demo_flash());
    let mut stack = Stack::new();
    apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
    let mut total: u64 = 0;
    while total < cycle_target {
        let cycles = step(&mut core, &mut stack)
            .expect("IRQ demo executes cleanly");
        total += cycles as u64;
    }
    core
}

#[test]
fn ipen_and_gie_round_trip_through_executor() {
    let core = run_demo(8);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(RCON_ADDR)) & RCON_IPEN,
        RCON_IPEN,
    );
    let intcon = core.memory.read_raw(Address::from_raw(INTCON_ADDR));
    assert_eq!(intcon & INTCON_GIE, INTCON_GIE);
    assert_eq!(intcon & INTCON_PEIE, INTCON_PEIE);
}

#[test]
fn no_pending_irq_when_no_flags_set() {
    let core = run_demo(8);
    assert!(!is_irq_pending(&core.memory));
}

#[test]
fn ipen0_compat_mode_peripheral_pending_high() {
    let mut core = Core::new(Variant::Pic18F25K20);
    let mut stack = Stack::new();
    apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
    // IPEN=0 (POR default), GIE=1, PEIE=1 (required for
    // peripheral sources in compat mode per DS section 9.1).
    core.memory.write_raw(
        Address::from_raw(INTCON_ADDR),
        INTCON_GIE | INTCON_PEIE,
    );
    core.memory.write_raw(Address::from_raw(PIE1_ADDR), 0x01);
    core.memory.write_raw(Address::from_raw(PIR1_ADDR), 0x01);
    assert!(is_irq_pending_high(&core.memory));
    assert!(!is_irq_pending_low(&core.memory));
}

#[test]
fn ipen1_priority_routing() {
    let mut core = Core::new(Variant::Pic18F25K20);
    let mut stack = Stack::new();
    apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
    core.memory.write_raw(Address::from_raw(RCON_ADDR), RCON_IPEN);
    core.memory.write_raw(
        Address::from_raw(INTCON_ADDR),
        INTCON_GIE | INTCON_PEIE,
    );
    // TMR1: PIE=1, PIR=1.  Set IPR1.0=1 -> high.
    core.memory.write_raw(Address::from_raw(PIE1_ADDR), 0x01);
    core.memory.write_raw(Address::from_raw(PIR1_ADDR), 0x01);
    core.memory.write_raw(Address::from_raw(IPR1_ADDR), 0x01);
    assert!(is_irq_pending_high(&core.memory));
    assert!(!is_irq_pending_low(&core.memory));
    // Flip IPR1.0=0 -> low.
    core.memory.write_raw(Address::from_raw(IPR1_ADDR), 0x00);
    assert!(!is_irq_pending_high(&core.memory));
    assert!(is_irq_pending_low(&core.memory));
}

#[test]
fn no_pending_when_gie_clear() {
    let mut core = Core::new(Variant::Pic18F25K20);
    let mut stack = Stack::new();
    apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
    // GIE=0 with all flags + enables set.
    core.memory.write_raw(Address::from_raw(INTCON_ADDR), 0);
    core.memory.write_raw(Address::from_raw(PIE1_ADDR), 0xFF);
    core.memory.write_raw(Address::from_raw(PIR1_ADDR), 0xFF);
    assert!(!is_irq_pending(&core.memory));
}
