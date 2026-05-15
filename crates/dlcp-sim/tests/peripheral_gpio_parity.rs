//! P2.6 / FID-14 GPIO peripheral parity gate.
//!
//! Phase-2 started with TRIS / LAT storage.  FID-14 closes the
//! silicon-fidelity gap from `docs/SIM_REWRITE_RUST_SPEC.md` §11c:
//! PORT/TRIS/LAT electrical reads, analog-vs-digital muxing, INTx /
//! RB interrupt-on-change edges, MCLR hold/release, RA0 wake, RC4/RC5
//! USB ownership, and `couple_pin` propagation.  Datasheet anchors:
//! DS40001303H §10 I/O Ports / §9 Interrupts / Table 5-2 ANSEL notes,
//! and DS39632E §10 I/O Ports plus the USB RC4/RC5 pin-sharing notes.

use dlcp_sim::RunState;
use dlcp_sim::chain::Chain;
use dlcp_sim::core::Core;
use dlcp_sim::exec::step;
use dlcp_sim::memory::{Address, Variant};
use dlcp_sim::pinnet::{PinId, PortLetter};
use dlcp_sim::reset::{ResetSource, apply_reset};
use dlcp_sim::stack::Stack;

const TRISA_ADDR: u16 = 0xF92;
const TRISB_ADDR: u16 = 0xF93;
const TRISC_ADDR: u16 = 0xF94;
const PORTA_ADDR: u16 = 0xF80;
const PORTB_ADDR: u16 = 0xF81;
const PORTC_ADDR: u16 = 0xF82;
const LATA_ADDR: u16 = 0xF89;
const LATB_ADDR: u16 = 0xF8A;
const LATC_ADDR: u16 = 0xF8B;
const ANSEL_ADDR: u16 = 0xF7E;
const ANSELH_ADDR: u16 = 0xF7F;
const UCON_ADDR: u16 = 0xF6D;
const INTCON_ADDR: u16 = 0xFF2;
const INTCON2_ADDR: u16 = 0xFF1;
const INTCON3_ADDR: u16 = 0xFF0;

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

fn build_gpio_output_flash() -> Vec<u8> {
    let mut flash = vec![0u8; 32 * 1024];
    let prog: &[(u32, [u8; 2])] = &[
        (0x0000, encode_movlw(0x00)),
        (0x0002, encode_movwf(0x94)), // TRISC = all output
        (0x0004, encode_movlw(0x01)),
        (0x0006, encode_movwf(0x8B)), // LATC0 = 1
        (0x0008, [0xFF, 0xD7]),       // BRA -1
    ];
    for (a, bytes) in prog {
        flash[*a as usize] = bytes[0];
        flash[*a as usize + 1] = bytes[1];
    }
    flash
}

fn build_self_loop_flash() -> Vec<u8> {
    let mut flash = vec![0u8; 32 * 1024];
    flash[0] = 0xFF;
    flash[1] = 0xD7;
    flash
}

fn sfr_write(core: &mut Core, addr: u16, value: u8) {
    core.memory.write_raw(Address::from_raw(addr), value);
    let memory = &mut core.memory;
    let peripherals = &mut core.peripherals;
    peripherals.on_sfr_write(addr, value, memory);
}

fn run_demo(cycle_target: u64) -> Core {
    let mut core = Core::new(Variant::Pic18F25K20);
    core.flash_mut().copy_from_slice(&build_gpio_demo_flash());
    let mut stack = Stack::new();
    apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
    let mut total: u64 = 0;
    while total < cycle_target {
        let cycles = step(&mut core, &mut stack).expect("GPIO demo executes cleanly");
        total += cycles as u64;
    }
    core
}

#[test]
fn trisb_write_round_trips() {
    let core = run_demo(8);
    assert_eq!(core.memory.read_raw(Address::from_raw(TRISB_ADDR)), 0x00,);
}

#[test]
fn latb_write_round_trips() {
    let core = run_demo(8);
    assert_eq!(core.memory.read_raw(Address::from_raw(LATB_ADDR)), 0xA5,);
}

#[test]
fn trisc_write_round_trips() {
    let core = run_demo(20);
    assert_eq!(core.memory.read_raw(Address::from_raw(TRISC_ADDR)), 0xC3,);
}

/// K20 POR resolves TRISA from CONFIG1H/FOSC.  The default
/// test config decodes as XT, so RA6/RA7 are oscillator pins
/// and read back disabled per DS40001303H Table 5-2 note 5.
#[test]
fn trisa_por_value_matches_k20_table() {
    let core = run_demo(1);
    assert_eq!(core.memory.read_raw(Address::from_raw(TRISA_ADDR)), 0x3F,);
}

/// LATA / LATC start at POR `xxxx xxxx` (= 0 in our model).
/// Confirm.
#[test]
fn lat_initial_state_after_por_is_zero() {
    let core = run_demo(1);
    assert_eq!(core.memory.read_raw(Address::from_raw(LATA_ADDR)), 0);
    assert_eq!(core.memory.read_raw(Address::from_raw(LATC_ADDR)), 0);
}

#[test]
fn port_tris_lat_analog_and_usb_policy_cover_fid14() {
    let mut chain = Chain::new();
    let idx = chain.push_core(Core::new(Variant::Pic18F25K20));
    chain.apply_reset_all(ResetSource::PowerOn);

    // DS40001303H §10: LAT drives PORT only when TRIS marks the bit
    // as an output; external levels are visible through input pins.
    sfr_write(&mut chain.cores[idx], TRISB_ADDR, 0xF0);
    for bit in 4..=7 {
        chain.set_pin_high(idx, PortLetter::B, bit);
    }
    sfr_write(&mut chain.cores[idx], LATB_ADDR, 0x0A);
    assert_eq!(
        chain.cores[idx]
            .memory
            .read_raw(Address::from_raw(PORTB_ADDR)),
        0xFA,
        "input RB7..RB4 preserve external level; output RB3..RB0 mirror LATB"
    );

    // Table 5-2 ANSEL notes: analog-selected inputs disable the
    // digital PORT read; clearing ANSEL makes the injected level visible.
    sfr_write(&mut chain.cores[idx], TRISA_ADDR, 0x01);
    sfr_write(&mut chain.cores[idx], ANSEL_ADDR, 0x01);
    chain.set_pin_high(idx, PortLetter::A, 0);
    assert_eq!(
        chain.cores[idx]
            .memory
            .read_raw(Address::from_raw(PORTA_ADDR))
            & 0x01,
        0,
        "RA0 analog mode must not read back as a digital high"
    );
    sfr_write(&mut chain.cores[idx], ANSEL_ADDR, 0x00);
    chain.set_pin_high(idx, PortLetter::A, 0);
    assert_eq!(
        chain.cores[idx]
            .memory
            .read_raw(Address::from_raw(PORTA_ADDR))
            & 0x01,
        0x01,
        "RA0 digital input must expose the injected high level"
    );

    // DS39632E USB pin sharing: when USBEN is set, RC4/RC5 are
    // peripheral-owned D-/D+ pins, not ordinary LATC-driven GPIO.
    let mut main = Core::new(Variant::Pic18F2455);
    let mut stack = Stack::new();
    apply_reset(&mut main, &mut stack, ResetSource::PowerOn);
    sfr_write(&mut main, TRISC_ADDR, 0x00);
    sfr_write(&mut main, UCON_ADDR, 0x08);
    sfr_write(&mut main, LATC_ADDR, 0x10);
    assert_eq!(
        main.memory.read_raw(Address::from_raw(PORTC_ADDR)) & 0x10,
        0,
        "USB-owned RC4 must not mirror LATC while UCON.USBEN is set"
    );
    sfr_write(&mut main, UCON_ADDR, 0x00);
    sfr_write(&mut main, LATC_ADDR, 0x10);
    assert_eq!(
        main.memory.read_raw(Address::from_raw(PORTC_ADDR)) & 0x10,
        0x10,
        "RC4 returns to GPIO output semantics when USB is disabled"
    );
}

#[test]
fn external_edges_ra0_wake_mclr_and_pin_coupling_cover_fid14() {
    let mut chain = Chain::new();
    let idx = chain.push_core(Core::new(Variant::Pic18F25K20));
    chain.apply_reset_all(ResetSource::PowerOn);

    // DS40001303H §9: INT0/1/2 respect INTEDG0/1/2, and RB7..RB4
    // interrupt-on-change sets RBIF when the sampled input changes.
    sfr_write(&mut chain.cores[idx], TRISB_ADDR, 0xFF);
    sfr_write(&mut chain.cores[idx], ANSELH_ADDR, 0x00);
    chain.cores[idx]
        .memory
        .write_raw(Address::from_raw(PORTB_ADDR), 0x00);
    chain.cores[idx]
        .memory
        .write_raw(Address::from_raw(INTCON2_ADDR), 0xF5);
    chain.set_pin_high(idx, PortLetter::B, 0);
    chain.set_pin_high(idx, PortLetter::B, 1);
    chain.set_pin_high(idx, PortLetter::B, 2);
    chain.set_pin_high(idx, PortLetter::B, 4);
    let intcon = chain.cores[idx]
        .memory
        .read_raw(Address::from_raw(INTCON_ADDR));
    let intcon3 = chain.cores[idx]
        .memory
        .read_raw(Address::from_raw(INTCON3_ADDR));
    assert_ne!(intcon & 0x02, 0, "RB0 rising edge sets INT0IF");
    assert_ne!(intcon3 & 0x01, 0, "RB1 rising edge sets INT1IF");
    assert_ne!(intcon3 & 0x02, 0, "RB2 rising edge sets INT2IF");
    assert_ne!(intcon & 0x01, 0, "RB4 change sets RBIF");

    // DLCP wake line: RA0 edge wakes a halted core so the scheduler can
    // re-enter instruction dispatch after Sleep/Idle.
    sfr_write(&mut chain.cores[idx], TRISA_ADDR, 0x01);
    sfr_write(&mut chain.cores[idx], ANSEL_ADDR, 0x00);
    chain.cores[idx].run_state = RunState::Sleep;
    chain.set_pin_low(idx, PortLetter::A, 0);
    chain.set_pin_high(idx, PortLetter::A, 0);
    assert_eq!(chain.cores[idx].run_state, RunState::Running);

    // MCLR low applies reset state and holds the CPU until release; release
    // plus re-bootstrap resumes from the reset vector.
    let mut reset_chain = Chain::new();
    let mut reset_core = Core::new(Variant::Pic18F25K20);
    reset_core
        .flash_mut()
        .copy_from_slice(&build_self_loop_flash());
    let reset_idx = reset_chain.push_core(reset_core);
    reset_chain.apply_reset_all(ResetSource::PowerOn);
    reset_chain.schedule_initial_steps(&[0]);
    reset_chain.step_ticks(1000);
    assert!(reset_chain.cores[reset_idx].cycles() > 0);
    reset_chain.hold_core_in_reset(reset_idx);
    assert!(reset_chain.cores[reset_idx].mclr_held);
    assert_eq!(reset_chain.cores[reset_idx].pc(), 0);
    assert_eq!(reset_chain.cores[reset_idx].cycles(), 0);
    reset_chain.step_ticks(1000);
    assert_eq!(reset_chain.cores[reset_idx].cycles(), 0);
    reset_chain.release_core_from_reset(reset_idx);
    reset_chain.schedule_initial_steps(&[0]);
    reset_chain.step_ticks(1000);
    assert!(reset_chain.cores[reset_idx].cycles() > 0);

    // `couple_pin` propagation: source LATC0 drives destination RB4 once;
    // clearing RBIF after the first transition must stay clear while the
    // source remains high in its steady-state self-loop.
    let mut pin_chain = Chain::new();
    let mut src = Core::new(Variant::Pic18F25K20);
    src.flash_mut().copy_from_slice(&build_gpio_output_flash());
    let src_idx = pin_chain.push_core(src);
    let dst_idx = pin_chain.push_core(Core::new(Variant::Pic18F25K20));
    pin_chain.apply_reset_all(ResetSource::PowerOn);
    sfr_write(&mut pin_chain.cores[dst_idx], TRISB_ADDR, 0xFF);
    sfr_write(&mut pin_chain.cores[dst_idx], ANSELH_ADDR, 0x00);
    pin_chain.cores[dst_idx]
        .memory
        .write_raw(Address::from_raw(PORTB_ADDR), 0x00);
    pin_chain.couple_pin(
        src_idx,
        PinId {
            port: PortLetter::C,
            bit: 0,
        },
        dst_idx,
        PinId {
            port: PortLetter::B,
            bit: 4,
        },
    );
    pin_chain.schedule_initial_steps(&[0, 0]);
    pin_chain.step_ticks(500);
    assert_ne!(
        pin_chain.cores[dst_idx]
            .memory
            .read_raw(Address::from_raw(PORTB_ADDR))
            & 0x10,
        0,
        "coupled destination RB4 follows source LATC0"
    );
    let cleared_rbif = pin_chain.cores[dst_idx]
        .memory
        .read_raw(Address::from_raw(INTCON_ADDR))
        & !0x01;
    pin_chain.cores[dst_idx]
        .memory
        .write_raw(Address::from_raw(INTCON_ADDR), cleared_rbif);
    pin_chain.step_ticks(500);
    assert_eq!(
        pin_chain.cores[dst_idx]
            .memory
            .read_raw(Address::from_raw(INTCON_ADDR))
            & 0x01,
        0,
        "steady high source must not keep reasserting RBIF"
    );
}
