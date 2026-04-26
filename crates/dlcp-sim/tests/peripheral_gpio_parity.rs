//! P2.6 GPIO peripheral parity gate.
//!
//! Phase-2 GPIO is minimum-viable: TRIS / LAT / PORT SFRs
//! round-trip through SFR memory with the existing
//! `apply_sfr_sw_write` masks.  Pin-coupling primitive
//! (`pinnet.rs`) and cross-core pin-to-pin propagation are
//! Phase-3 work.

use dlcp_sim::core::Core;
use dlcp_sim::exec::step;
use dlcp_sim::memory::{Address, Variant};
use dlcp_sim::reset::{ResetSource, apply_reset};
use dlcp_sim::stack::Stack;

const TRISA_ADDR: u16 = 0xF92;
const TRISB_ADDR: u16 = 0xF93;
const TRISC_ADDR: u16 = 0xF94;
const LATA_ADDR: u16 = 0xF89;
const LATB_ADDR: u16 = 0xF8A;
const LATC_ADDR: u16 = 0xF8B;

fn encode_movlw(k: u8) -> [u8; 2] {
    [k, 0x0E]
}
fn encode_movwf(f: u8) -> [u8; 2] {
    let word = 0x6E00u16 | (f as u16);
    [word as u8, (word >> 8) as u8]
}

fn build_gpio_demo_flash() -> Vec<u8> {
    let mut flash = vec![0u8; 32 * 1024];
    // Set TRISB to 0x00 (all output), LATB to 0xA5.
    let prog: &[(u32, [u8; 2])] = &[
        (0x0000, encode_movlw(0x00)),
        (0x0002, encode_movwf(0x93)), // TRISB
        (0x0004, encode_movlw(0xA5)),
        (0x0006, encode_movwf(0x8A)), // LATB
        (0x0008, encode_movlw(0xC3)),
        (0x000A, encode_movwf(0x94)), // TRISC = 0xC3 (mixed I/O)
        (0x000C, [0xFF, 0xD7]),       // BRA -1
    ];
    for (a, bytes) in prog {
        flash[*a as usize] = bytes[0];
        flash[*a as usize + 1] = bytes[1];
    }
    flash
}

fn run_demo(cycle_target: u64) -> Core {
    let mut core = Core::new(Variant::Pic18F25K20);
    core.flash_mut().copy_from_slice(&build_gpio_demo_flash());
    let mut stack = Stack::new();
    apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
    let mut total: u64 = 0;
    while total < cycle_target {
        let cycles = step(&mut core, &mut stack)
            .expect("GPIO demo executes cleanly");
        total += cycles as u64;
    }
    core
}

#[test]
fn trisb_write_round_trips() {
    let core = run_demo(8);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(TRISB_ADDR)),
        0x00,
    );
}

#[test]
fn latb_write_round_trips() {
    let core = run_demo(8);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(LATB_ADDR)),
        0xA5,
    );
}

#[test]
fn trisc_write_round_trips() {
    let core = run_demo(20);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(TRISC_ADDR)),
        0xC3,
    );
}

/// K20 POR sets TRISA = 0x7F (Note 5: RA7 disabled in INTOSC
/// modes; this codebase's K20_POR captures the
/// firmware-observable post-reset value).
#[test]
fn trisa_por_value_matches_k20_table() {
    let core = run_demo(1);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(TRISA_ADDR)),
        0x7F,
    );
}

/// LATA / LATC start at POR `xxxx xxxx` (= 0 in our model).
/// Confirm.
#[test]
fn lat_initial_state_after_por_is_zero() {
    let core = run_demo(1);
    assert_eq!(core.memory.read_raw(Address::from_raw(LATA_ADDR)), 0);
    assert_eq!(core.memory.read_raw(Address::from_raw(LATC_ADDR)), 0);
}
