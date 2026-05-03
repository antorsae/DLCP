//! P2.3 Timer0 / Timer3 peripheral parity gate.
//!
//! Phase-2 single-core scope: SFR-write reactivity, internal-
//! clock-source counting at the Tcy granularity scaled by the
//! prescaler, and the 8-bit / 16-bit overflow + IRQ-flag
//! semantics firmware observes via INTCON.TMR0IF and
//! PIR2.TMR3IF.  External pin sources and 16-bit latched-
//! buffer reads are Phase-3 / P2.7 work.

use dlcp_sim::core::{Core, RunState};
use dlcp_sim::exec::step;
use dlcp_sim::memory::{Address, Variant};
use dlcp_sim::peripherals::timer::{
    INTCON_ADDR, PIR1_ADDR, PIR2_ADDR, PR2_ADDR, T0CON_ADDR, T1CON_ADDR, T2CON_ADDR, T3CON_ADDR,
    TMR0H_ADDR, TMR0L_ADDR, TMR1H_ADDR, TMR1L_ADDR, TMR2_ADDR, TMR3H_ADDR, TMR3L_ADDR,
};
use dlcp_sim::reset::{ResetSource, apply_reset};
use dlcp_sim::stack::Stack;

const T0CON_TMR0ON: u8 = 1 << 7;
const T0CON_T08BIT: u8 = 1 << 6;
const T0CON_T0CS: u8 = 1 << 5;
const T0CON_PSA: u8 = 1 << 3;
const T1CON_RD16: u8 = 1 << 7;
const T1CON_TMR1CS: u8 = 1 << 1;
const T1CON_TMR1ON: u8 = 1 << 0;
const T2CON_TMR2ON: u8 = 1 << 2;
const T2CON_T2OUTPS_SHIFT: u8 = 3;
const T3CON_TMR3ON: u8 = 1 << 0;
const T3CON_RD16: u8 = 1 << 7;
const T3CON_TMR3CS: u8 = 1 << 1;
const INTCON_TMR0IF: u8 = 1 << 2;
const PIR1_TMR1IF: u8 = 1 << 0;
const PIR1_TMR2IF: u8 = 1 << 1;
const PIR2_TMR3IF: u8 = 1 << 1;

fn encode_movlw(k: u8) -> [u8; 2] {
    [k, 0x0E]
}
fn encode_movwf(f: u8) -> [u8; 2] {
    let word = 0x6E00u16 | (f as u16);
    [word as u8, (word >> 8) as u8]
}

/// Build a flash image that:
///   1. enables Timer0 in 8-bit mode with 1:1 prescaler
///   2. loops indefinitely so Tcy keeps accumulating
fn build_timer0_8bit_demo_flash() -> Vec<u8> {
    let mut flash = vec![0u8; 32 * 1024];
    let prog: &[(u32, [u8; 2])] = &[
        (0x0000, encode_movlw(T0CON_TMR0ON | T0CON_T08BIT | T0CON_PSA)),
        (0x0002, encode_movwf(0xD5)), // T0CON @ 0xFD5
        (0x0004, [0xFF, 0xD7]),       // BRA -1 self-loop
    ];
    for (addr, bytes) in prog {
        flash[*addr as usize] = bytes[0];
        flash[*addr as usize + 1] = bytes[1];
    }
    flash
}

fn build_timer3_demo_flash() -> Vec<u8> {
    let mut flash = vec![0u8; 32 * 1024];
    let prog: &[(u32, [u8; 2])] = &[
        (0x0000, encode_movlw(T3CON_TMR3ON)),
        (0x0002, encode_movwf(0xB1)), // T3CON @ 0xFB1
        (0x0004, [0xFF, 0xD7]),
    ];
    for (addr, bytes) in prog {
        flash[*addr as usize] = bytes[0];
        flash[*addr as usize + 1] = bytes[1];
    }
    flash
}

fn run_demo(flash: Vec<u8>, cycle_target: u64) -> Core {
    let mut core = Core::new(Variant::Pic18F25K20);
    core.flash_mut().copy_from_slice(&flash);
    let mut stack = Stack::new();
    apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
    let mut total: u64 = 0;
    while total < cycle_target {
        let cycles = step(&mut core, &mut stack)
            .expect("timer demo executes cleanly");
        total += cycles as u64;
    }
    core
}

#[test]
fn timer0_increments_during_bra_loop() {
    // Setup is 2 instructions = 2 Tcy.  After 50 total Tcy
    // we've spent ~48 Tcy in the BRA loop.  Timer0 8-bit
    // 1:1 -> TMR0L should be ~48 (give or take a Tcy for
    // when the timer was actually enabled).
    let core = run_demo(build_timer0_8bit_demo_flash(), 50);
    let tmr0l = core.memory.read_raw(Address::from_raw(TMR0L_ADDR));
    assert!(
        tmr0l > 30 && tmr0l < 60,
        "TMR0L should reflect ~48 Tcy of counting (got {tmr0l})"
    );
}

#[test]
fn timer0_overflow_sets_tmr0if_via_executor() {
    // 256 Tcy + setup overhead -> at least one wrap.
    let core = run_demo(build_timer0_8bit_demo_flash(), 300);
    let intcon = core.memory.read_raw(Address::from_raw(INTCON_ADDR));
    assert_eq!(
        intcon & INTCON_TMR0IF,
        INTCON_TMR0IF,
        "TMR0IF must assert after 256 Tcy of 1:1 prescaler"
    );
}

#[test]
fn timer3_increments_at_internal_clock() {
    let core = run_demo(build_timer3_demo_flash(), 50);
    let tmr3l = core.memory.read_raw(Address::from_raw(TMR3L_ADDR));
    assert!(
        tmr3l > 30 && tmr3l < 60,
        "TMR3L should reflect ~48 Tcy of counting (got {tmr3l})"
    );
}

#[test]
fn timer3_overflow_sets_tmr3if_after_65536_tcy() {
    let core = run_demo(build_timer3_demo_flash(), 70_000);
    let pir2 = core.memory.read_raw(Address::from_raw(PIR2_ADDR));
    assert_eq!(
        pir2 & PIR2_TMR3IF,
        PIR2_TMR3IF,
        "TMR3IF must assert after 65536 Tcy of 1:1 prescaler"
    );
}

#[test]
fn timer0_disabled_does_not_count() {
    // K20 POR sets T0CON=0xFF (TMR0ON=1).  To verify the
    // "disabled timer doesn't tick" path we have to
    // explicitly clear T0CON via firmware.
    let mut flash = vec![0u8; 32 * 1024];
    let prog: &[(u32, [u8; 2])] = &[
        // CLRF T0CON, a=0  -- opcode 0x6Aff for a=0
        (0x0000, [0xD5, 0x6A]),
        (0x0002, [0xFF, 0xD7]), // BRA -1 self-loop
    ];
    for (addr, bytes) in prog {
        flash[*addr as usize] = bytes[0];
        flash[*addr as usize + 1] = bytes[1];
    }
    let core = run_demo(flash, 1000);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(TMR0L_ADDR)),
        0,
        "TMR0L must not count after T0CON cleared"
    );
    assert_eq!(
        core.memory.read_raw(Address::from_raw(T0CON_ADDR)) & T0CON_TMR0ON,
        0,
    );
}

#[test]
fn timer1_timer2_and_special_event_reset_cover_fid09() {
    // §11c FID-09: Timer1 and Timer2 must be visible where
    // firmware/tests can observe them.  DS40001303H/DS39632E
    // timer chapters define Timer1 as a 16-bit counter with
    // TMR1IF overflow and Timer2 as TMR2/PR2 plus prescaler
    // and postscaler driving TMR2IF.
    let mut core = Core::new(Variant::Pic18F25K20);

    core.memory.write_raw(Address::from_raw(T1CON_ADDR), T1CON_TMR1ON);
    core.peripherals
        .timers
        .on_sfr_write(T1CON_ADDR, T1CON_TMR1ON, &mut core.memory);
    core.memory.write_raw(Address::from_raw(TMR1H_ADDR), 0xFF);
    core.peripherals
        .timers
        .on_sfr_write(TMR1H_ADDR, 0xFF, &mut core.memory);
    core.memory.write_raw(Address::from_raw(TMR1L_ADDR), 0xFE);
    core.peripherals.tick_tcy(2, &mut core.memory);
    assert_eq!(core.memory.read_raw(Address::from_raw(TMR1L_ADDR)), 0);
    assert_eq!(core.memory.read_raw(Address::from_raw(TMR1H_ADDR)), 0);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(PIR1_ADDR)) & PIR1_TMR1IF,
        PIR1_TMR1IF,
        "Timer1 overflow asserts PIR1.TMR1IF"
    );

    core.memory.write_raw(Address::from_raw(TMR1H_ADDR), 0x12);
    core.peripherals
        .timers
        .on_sfr_write(TMR1H_ADDR, 0x12, &mut core.memory);
    core.memory.write_raw(Address::from_raw(TMR1L_ADDR), 0x34);
    core.peripherals
        .timers
        .reset_timer1_for_special_event(&mut core.memory);
    assert_eq!(core.memory.read_raw(Address::from_raw(TMR1L_ADDR)), 0);
    assert_eq!(core.memory.read_raw(Address::from_raw(TMR1H_ADDR)), 0);

    core.memory.write_raw(Address::from_raw(PR2_ADDR), 3);
    core.memory.write_raw(
        Address::from_raw(T2CON_ADDR),
        T2CON_TMR2ON | (1 << T2CON_T2OUTPS_SHIFT),
    );
    core.peripherals.tick_tcy(4, &mut core.memory);
    assert_eq!(core.memory.read_raw(Address::from_raw(TMR2_ADDR)), 0);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(PIR1_ADDR)) & PIR1_TMR2IF,
        0,
        "first PR2 match is swallowed by 1:2 postscaler"
    );
    core.peripherals.tick_tcy(4, &mut core.memory);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(PIR1_ADDR)) & PIR1_TMR2IF,
        PIR1_TMR2IF,
        "second PR2 match asserts TMR2IF through postscaler"
    );
}

#[test]
fn timer_latches_external_edges_and_idle_behavior_cover_fid09() {
    // §11c FID-09: Timer0/1/3 16-bit read latches, explicit
    // external-edge hooks for T0CKI and T1OSC/T13CKI, and
    // sleep-vs-idle timer behavior are all silicon-visible
    // semantics in DS39632E/DS40001303H timer and power
    // management chapters.
    let mut core = Core::new(Variant::Pic18F25K20);

    core.memory.write_raw(
        Address::from_raw(T0CON_ADDR),
        T0CON_TMR0ON | T0CON_PSA,
    );
    core.peripherals.tick_tcy(0x0123, &mut core.memory);
    core.peripherals
        .timers
        .on_sfr_read(TMR0L_ADDR, &mut core.memory);
    assert_eq!(core.memory.read_raw(Address::from_raw(TMR0L_ADDR)), 0x23);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(TMR0H_ADDR)),
        0x01,
        "TMR0L read latches the live Timer0 high byte"
    );
    core.peripherals.tick_tcy(0x0100, &mut core.memory);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(TMR0H_ADDR)),
        0x01,
        "latched TMR0H stays stable until the next TMR0L read"
    );

    core.memory.write_raw(
        Address::from_raw(T3CON_ADDR),
        T3CON_TMR3ON | T3CON_RD16,
    );
    core.peripherals
        .timers
        .on_sfr_write(T3CON_ADDR, T3CON_TMR3ON | T3CON_RD16, &mut core.memory);
    core.peripherals.tick_tcy(0x0456, &mut core.memory);
    core.peripherals
        .timers
        .on_sfr_read(TMR3L_ADDR, &mut core.memory);
    assert_eq!(core.memory.read_raw(Address::from_raw(TMR3H_ADDR)), 0x04);
    core.peripherals
        .timers
        .reset_timer3_for_special_event(&mut core.memory);
    assert_eq!(core.memory.read_raw(Address::from_raw(TMR3L_ADDR)), 0);
    assert_eq!(core.memory.read_raw(Address::from_raw(TMR3H_ADDR)), 0);

    core.memory.write_raw(
        Address::from_raw(T1CON_ADDR),
        T1CON_TMR1ON | T1CON_RD16,
    );
    core.peripherals
        .timers
        .on_sfr_write(T1CON_ADDR, T1CON_TMR1ON | T1CON_RD16, &mut core.memory);
    core.peripherals.tick_tcy(0x0201, &mut core.memory);
    core.peripherals
        .timers
        .on_sfr_read(TMR1L_ADDR, &mut core.memory);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(TMR1H_ADDR)),
        0x02,
        "TMR1L read latches the live Timer1 high byte in RD16 mode"
    );
    core.peripherals
        .timers
        .reset_timer1_for_special_event(&mut core.memory);

    core.memory.write_raw(
        Address::from_raw(T0CON_ADDR),
        T0CON_TMR0ON | T0CON_T08BIT | T0CON_T0CS | T0CON_PSA,
    );
    core.memory.write_raw(Address::from_raw(TMR0L_ADDR), 0);
    core.peripherals.tick_tcy(10, &mut core.memory);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(TMR0L_ADDR)),
        0,
        "internal Tcy must not advance Timer0 when T0CS selects T0CKI"
    );
    core.peripherals
        .timers
        .inject_t0cki_rising_edge(&mut core.memory);
    assert_eq!(core.memory.read_raw(Address::from_raw(TMR0L_ADDR)), 1);

    core.memory.write_raw(
        Address::from_raw(T1CON_ADDR),
        T1CON_TMR1ON | T1CON_TMR1CS,
    );
    core.peripherals
        .timers
        .on_sfr_write(T1CON_ADDR, T1CON_TMR1ON | T1CON_TMR1CS, &mut core.memory);
    core.memory.write_raw(Address::from_raw(TMR1L_ADDR), 0);
    core.peripherals
        .timers
        .reset_timer3_for_special_event(&mut core.memory);
    core.memory.write_raw(
        Address::from_raw(T3CON_ADDR),
        T3CON_TMR3ON | T3CON_TMR3CS,
    );
    core.peripherals
        .timers
        .on_sfr_write(T3CON_ADDR, T3CON_TMR3ON | T3CON_TMR3CS, &mut core.memory);
    core.peripherals.tick_tcy(10, &mut core.memory);
    assert_eq!(core.memory.read_raw(Address::from_raw(TMR1L_ADDR)), 0);
    assert_eq!(core.memory.read_raw(Address::from_raw(TMR3L_ADDR)), 0);
    core.peripherals
        .timers
        .inject_t1osc_t13cki_rising_edge(&mut core.memory);
    assert_eq!(core.memory.read_raw(Address::from_raw(TMR1L_ADDR)), 1);
    assert_eq!(core.memory.read_raw(Address::from_raw(TMR3L_ADDR)), 1);

    core.memory.write_raw(Address::from_raw(PR2_ADDR), 0xFF);
    core.memory.write_raw(Address::from_raw(TMR2_ADDR), 0);
    core.memory
        .write_raw(Address::from_raw(T2CON_ADDR), T2CON_TMR2ON);
    core.run_state = RunState::Idle;
    core.advance_halted_cycles(3);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(TMR2_ADDR)),
        3,
        "idle mode keeps peripheral clocks advancing"
    );
    core.run_state = RunState::Sleep;
    core.advance_halted_cycles(3);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(TMR2_ADDR)),
        3,
        "sleep mode stops normal peripheral timer clocks"
    );
}
