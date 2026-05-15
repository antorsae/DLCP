//! P2.7 IRQ controller parity gate.
//!
//! Phase-2 IRQ is a query surface only -- the executor does
//! not yet vector to 0x0008 / 0x0018 on a pending IRQ.  These
//! tests assert the SFR semantics + `is_irq_pending` priority
//! decisions for the documented PIE/PIR/GIE/IPEN combos.

use dlcp_sim::core::{Core, RunState};
use dlcp_sim::exec::step;
use dlcp_sim::memory::{Address, Variant};
use dlcp_sim::peripherals::irq::{
    INTCON_ADDR, IPR1_ADDR, IRQ_VECTOR_HIGH, IRQ_VECTOR_LOW, PIE1_ADDR, PIR1_ADDR, RCON_ADDR,
    is_irq_pending, is_irq_pending_high, is_irq_pending_low,
};
use dlcp_sim::reset::{ResetSource, apply_reset};
use dlcp_sim::stack::Stack;

const INTCON_GIE: u8 = 1 << 7;
const INTCON_PEIE: u8 = 1 << 6;
const RCON_IPEN: u8 = 1 << 7;
const RCON_TO: u8 = 1 << 3;
const RCON_PD: u8 = 1 << 2;
const WDTCON_ADDR: u16 = 0xFD1;
const OSCCON_ADDR: u16 = 0xFD3;
const PIE1_TMR1IE: u8 = 1 << 0;
const PIE1_TMR2IE: u8 = 1 << 1;
const PIR1_TMR1IF: u8 = 1 << 0;
const PIR1_TMR2IF: u8 = 1 << 1;

fn encode_movlw(k: u8) -> [u8; 2] {
    [k, 0x0E]
}
fn encode_movwf(f: u8) -> [u8; 2] {
    let word = 0x6E00u16 | (f as u16);
    [word as u8, (word >> 8) as u8]
}
fn encode_clrwdt() -> [u8; 2] {
    [0x04, 0x00]
}
fn encode_sleep() -> [u8; 2] {
    [0x03, 0x00]
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
        let cycles = step(&mut core, &mut stack).expect("IRQ demo executes cleanly");
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
    core.memory
        .write_raw(Address::from_raw(INTCON_ADDR), INTCON_GIE | INTCON_PEIE);
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
    core.memory
        .write_raw(Address::from_raw(RCON_ADDR), RCON_IPEN);
    core.memory
        .write_raw(Address::from_raw(INTCON_ADDR), INTCON_GIE | INTCON_PEIE);
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

#[test]
fn wdt_running_timeout_resets_and_clrwdt_clears() {
    // §11c FID-02: WDTEN/SWDTEN control the WDT; CONFIG2H.WDTPS
    // applies a postscale, and CLRWDT clears the counter and sets
    // RCON.TO/PD.  Datasheet anchors: DS40001303H §23.2 says the
    // nominal 4 ms WDT period is postscaled by WDTPS and CLRWDT
    // clears WDT/postscaler; DS39632E instruction table gives
    // CLRWDT status effects.
    let mut core = Core::new(Variant::Pic18F25K20);
    let mut cfg = [0u8; dlcp_sim::config::CONFIG_BYTES];
    cfg[3] = 1; // WDTEN=1, WDTPS=0000 (1:1)
    core.config = dlcp_sim::Config::from_bytes(cfg);
    core.flash_mut()[0..2].copy_from_slice(&encode_clrwdt());
    let mut stack = Stack::new();
    apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
    core.config = dlcp_sim::Config::from_bytes(cfg);
    core.advance_cycles((core.wdt_timeout_tcy() - 1) as u32);
    assert!(core.wdt_counter_tcy() > 0);
    step(&mut core, &mut stack).expect("CLRWDT executes");
    assert_eq!(core.wdt_counter_tcy(), 0, "CLRWDT clears WDT/postscaler");
    let rcon = core.memory.read_raw(Address::from_raw(RCON_ADDR));
    assert_eq!(rcon & (RCON_TO | RCON_PD), RCON_TO | RCON_PD);

    core.flash_mut()[0..2].copy_from_slice(&[0x00, 0x00]); // NOP
    core.set_pc(0);
    core.advance_cycles(core.wdt_timeout_tcy() as u32);
    step(&mut core, &mut stack).expect("pending WDT reset applies after instruction boundary");
    assert_eq!(core.pc(), 0, "running-mode WDT timeout resets PC");
    assert_eq!(core.run_state, RunState::Running);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(RCON_ADDR)) & RCON_TO,
        0,
        "WDT reset clears RCON.TO"
    );

    let mut sw = Core::new(Variant::Pic18F25K20);
    sw.memory.write_raw(Address::from_raw(WDTCON_ADDR), 0x01);
    assert!(sw.wdt_timeout_tcy() > 0);
    sw.advance_cycles(sw.wdt_timeout_tcy() as u32);
    assert!(
        sw.take_wdt_timeout_pending(),
        "SWDTEN=1 enables WDT when CONFIG2H.WDTEN=0"
    );
}

#[test]
fn sleep_idle_wake_tests() {
    // §11c FID-02/FID-13: SLEEP clears WDT/postscaler, sets
    // TO=1/PD=0, and halts instruction fetch.  OSCCON.IDLEN=1
    // selects Idle instead of Sleep.  DS40001303H §3.3 and
    // instruction SLEEP entry describe the halt/status behavior;
    // DS §23.2 says WDT timeout exits power-managed modes.
    let mut core = Core::new(Variant::Pic18F25K20);
    core.flash_mut()[0..4].copy_from_slice(&[encode_sleep(), encode_movlw(0x42)].concat());
    let mut stack = Stack::new();
    step(&mut core, &mut stack).expect("SLEEP executes");
    assert_eq!(core.run_state, RunState::Sleep);
    assert_eq!(core.pc(), 2);
    let rcon = core.memory.read_raw(Address::from_raw(RCON_ADDR));
    assert_eq!(rcon & RCON_TO, RCON_TO);
    assert_eq!(rcon & RCON_PD, 0);
    assert_eq!(
        step(&mut core, &mut stack).expect("sleeping step is quiescent"),
        0
    );
    assert_eq!(core.pc(), 2, "sleeping CPU must not fetch next instruction");
    assert_eq!(core.memory.read_raw(Address::from_raw(0xFE8)), 0);

    core.memory
        .write_raw(Address::from_raw(INTCON_ADDR), INTCON_GIE | INTCON_PEIE);
    core.memory.write_raw(Address::from_raw(PIE1_ADDR), 0x01);
    core.memory.write_raw(Address::from_raw(PIR1_ADDR), 0x01);
    let cycles = step(&mut core, &mut stack).expect("interrupt wakes sleeping core");
    assert_eq!(cycles, 2);
    assert_eq!(core.run_state, RunState::Running);
    assert_eq!(
        core.pc(),
        0x0008,
        "wake interrupt vectors before foreground fetch"
    );

    let mut idle = Core::new(Variant::Pic18F25K20);
    let mut cfg = [0u8; dlcp_sim::config::CONFIG_BYTES];
    cfg[3] = 1; // WDTEN=1, WDTPS=1:1
    idle.config = dlcp_sim::Config::from_bytes(cfg);
    idle.flash_mut()[0..4].copy_from_slice(&[encode_sleep(), encode_movlw(0x24)].concat());
    idle.memory.write_raw(Address::from_raw(OSCCON_ADDR), 0x80); // IDLEN
    let mut stack = Stack::new();
    step(&mut idle, &mut stack).expect("IDLEN sleep enters Idle");
    assert_eq!(idle.run_state, RunState::Idle);
    idle.advance_halted_cycles(idle.wdt_timeout_tcy() as u32);
    assert_eq!(idle.run_state, RunState::Running, "WDT timeout wakes Idle");
    assert_eq!(
        idle.memory.read_raw(Address::from_raw(RCON_ADDR)) & RCON_TO,
        0,
        "WDT wake clears TO"
    );
    step(&mut idle, &mut stack).expect("foreground resumes after Idle wake");
    assert_eq!(idle.memory.read_raw(Address::from_raw(0xFE8)), 0x24);
}

#[test]
fn nested_high_interrupt_over_low_restores_gates_by_context() {
    // §11c FID-13: in IPEN=1, a high-priority IRQ may preempt
    // a low-priority ISR.  RETFIE from the nested high ISR must
    // restore GIEH only, leaving GIEL disabled until the low ISR
    // itself returns.  DS39632E/DS40001303H §9.3 describes the
    // separate GIEH/GIEL gates and high-over-low preemption.
    let mut core = Core::new(Variant::Pic18F2455);
    let mut stack = Stack::new();
    core.flash_mut()[IRQ_VECTOR_HIGH as usize..IRQ_VECTOR_HIGH as usize + 2]
        .copy_from_slice(&[0x10, 0x00]); // RETFIE 0
    core.flash_mut()[IRQ_VECTOR_LOW as usize..IRQ_VECTOR_LOW as usize + 2]
        .copy_from_slice(&[0x10, 0x00]); // RETFIE 0
    core.set_pc(0x0040);
    core.memory
        .write_raw(Address::from_raw(RCON_ADDR), RCON_IPEN);
    core.memory
        .write_raw(Address::from_raw(INTCON_ADDR), INTCON_GIE | INTCON_PEIE);
    core.memory
        .write_raw(Address::from_raw(PIE1_ADDR), PIE1_TMR1IE | PIE1_TMR2IE);
    core.memory
        .write_raw(Address::from_raw(IPR1_ADDR), PIE1_TMR2IE);
    core.memory
        .write_raw(Address::from_raw(PIR1_ADDR), PIR1_TMR1IF);

    step(&mut core, &mut stack).expect("low interrupt dispatches");
    assert_eq!(core.pc(), IRQ_VECTOR_LOW);
    assert_eq!(stack.depth(), 1);
    let intcon = core.memory.read_raw(Address::from_raw(INTCON_ADDR));
    assert_eq!(intcon & INTCON_GIE, INTCON_GIE, "low ISR leaves GIEH set");
    assert_eq!(intcon & INTCON_PEIE, 0, "low ISR clears GIEL");

    core.memory
        .write_raw(Address::from_raw(PIR1_ADDR), PIR1_TMR1IF | PIR1_TMR2IF);
    step(&mut core, &mut stack).expect("high interrupt preempts low ISR");
    assert_eq!(core.pc(), IRQ_VECTOR_HIGH);
    assert_eq!(stack.depth(), 2);
    let intcon = core.memory.read_raw(Address::from_raw(INTCON_ADDR));
    assert_eq!(intcon & INTCON_GIE, 0, "high ISR clears GIEH");
    assert_eq!(
        intcon & INTCON_PEIE,
        0,
        "low gate remains clear during preemption"
    );

    core.memory
        .write_raw(Address::from_raw(PIR1_ADDR), PIR1_TMR1IF);
    step(&mut core, &mut stack).expect("nested high RETFIE returns to low ISR");
    assert_eq!(core.pc(), IRQ_VECTOR_LOW);
    assert_eq!(stack.depth(), 1);
    let intcon = core.memory.read_raw(Address::from_raw(INTCON_ADDR));
    assert_eq!(intcon & INTCON_GIE, INTCON_GIE);
    assert_eq!(
        intcon & INTCON_PEIE,
        0,
        "high RETFIE must not reopen low-priority nesting gate"
    );

    core.memory.write_raw(Address::from_raw(PIR1_ADDR), 0);
    step(&mut core, &mut stack).expect("low RETFIE returns to foreground");
    assert_eq!(core.pc(), 0x0040);
    assert_eq!(stack.depth(), 0);
    let intcon = core.memory.read_raw(Address::from_raw(INTCON_ADDR));
    assert_eq!(
        intcon & (INTCON_GIE | INTCON_PEIE),
        INTCON_GIE | INTCON_PEIE
    );
}
