//! P2.2 MSSP I²C peripheral parity gate.
//!
//! Phase-2 single-core scope: SFR-write reactivity, master
//! mode start/stop scheduling, and SCL-period-derived state-
//! machine progression.  Bit-level bus comparison against
//! gpsim's `i2c-regfile.cc` slave is Phase-4 dual-run work.
//!
//! These tests exercise the peripheral through the *real*
//! executor path (instructions writing through
//! `write_addr_masked`) to verify the Core ↔ Peripherals
//! plumbing dispatches MSSP-relevant SFR writes correctly.

use dlcp_sim::core::Core;
use dlcp_sim::exec::step;
use dlcp_sim::memory::{Address, Variant};
use dlcp_sim::peripherals::mssp::{
    I2cBusEvent, PIR1_ADDR, PIR2_ADDR, SSPADD_ADDR, SSPBUF_ADDR, SSPCON1_ADDR, SSPCON2_ADDR,
    SSPSTAT_ADDR,
};
use dlcp_sim::reset::{ResetSource, apply_reset};
use dlcp_sim::stack::Stack;

const SSPCON1_SSPEN: u8 = 1 << 5;
const SSPM_I2C_MASTER: u8 = 0b1000;
const SSPM_SPI_MASTER: u8 = 0b0010;
const SSPM_I2C_SLAVE_10BIT: u8 = 0b0111;
const SSPCON2_GCEN: u8 = 1 << 7;
const SSPCON2_SEN: u8 = 1 << 0;
const SSPCON2_RSEN: u8 = 1 << 1;
const SSPCON2_PEN: u8 = 1 << 2;
const PIR1_SSPIF: u8 = 1 << 3;
const PIR2_BCLIF: u8 = 1 << 3;

fn encode_movlw(k: u8) -> [u8; 2] {
    [k, 0x0E]
}

fn encode_movwf(f: u8) -> [u8; 2] {
    let word = 0x6E00u16 | (f as u16);
    [word as u8, (word >> 8) as u8]
}

fn build_mssp_demo_flash(sspadd: u8) -> Vec<u8> {
    let mut flash = vec![0u8; 32 * 1024];
    let program: &[(u32, [u8; 2])] = &[
        // SSPADD = sspadd
        (0x0000, encode_movlw(sspadd)),
        (0x0002, encode_movwf(0xC8)), // SSPADD @ 0xFC8
        // SSPCON1 = SSPEN | SSPM_I2C_MASTER
        (0x0004, encode_movlw(SSPCON1_SSPEN | SSPM_I2C_MASTER)),
        (0x0006, encode_movwf(0xC6)), // SSPCON1 @ 0xFC6
        // SSPCON2 = SEN (start condition)
        (0x0008, encode_movlw(SSPCON2_SEN)),
        (0x000A, encode_movwf(0xC5)), // SSPCON2 @ 0xFC5
        // BRA -1 (loop)
        (0x000C, [0xFF, 0xD7]),
    ];
    for (addr, bytes) in program {
        flash[*addr as usize] = bytes[0];
        flash[*addr as usize + 1] = bytes[1];
    }
    flash
}

fn run_mssp_demo(sspadd: u8, cycle_target: u64) -> Core {
    let mut core = Core::new(Variant::Pic18F2455);
    core.flash_mut().copy_from_slice(&build_mssp_demo_flash(sspadd));
    let mut stack = Stack::new();
    apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
    let mut total: u64 = 0;
    while total < cycle_target {
        let cycles = step(&mut core, &mut stack)
            .expect("MSSP demo program executes cleanly");
        total += cycles as u64;
    }
    core
}

/// SSPCON1.SSPEN must remain set after the firmware enables
/// the peripheral.  No HW-driven side effect should clear it
/// in the Phase-2 model.
#[test]
fn enabling_sspen_via_executor_persists() {
    let core = run_mssp_demo(0x77, 6); // run past the SSPCON1 write
    let con1 = core.memory.read_raw(Address::from_raw(SSPCON1_ADDR));
    assert_eq!(con1 & SSPCON1_SSPEN, SSPCON1_SSPEN);
    assert_eq!(con1 & 0x0F, SSPM_I2C_MASTER);
}

/// SSPADD=0x77 -> SCL period = 0x77+1 = 120 Tcy.  After SEN
/// write, the start condition completes in one full SCL
/// period.  At cycle 9 (post-SEN MOVWF, before 120 Tcy
/// elapse), the state machine is mid-start; SEN remains set.
#[test]
fn sen_pending_mid_window() {
    let core = run_mssp_demo(0x77, 9);
    let con2 = core.memory.read_raw(Address::from_raw(SSPCON2_ADDR));
    assert_eq!(con2 & SSPCON2_SEN, SSPCON2_SEN, "SEN still pending");
    let pir1 = core.memory.read_raw(Address::from_raw(PIR1_ADDR));
    assert_eq!(pir1 & PIR1_SSPIF, 0, "SSPIF not yet asserted");
}

/// After ~6 setup Tcy + 120 Tcy start sequence, SEN auto-
/// clears and SSPIF asserts.  Run a comfortable 200 Tcy past
/// setup.
#[test]
fn start_completes_clears_sen_sets_sspif() {
    let core = run_mssp_demo(0x77, 6 + 200);
    let con2 = core.memory.read_raw(Address::from_raw(SSPCON2_ADDR));
    assert_eq!(con2 & SSPCON2_SEN, 0, "SEN must auto-clear post-start");
    let pir1 = core.memory.read_raw(Address::from_raw(PIR1_ADDR));
    assert_eq!(pir1 & PIR1_SSPIF, PIR1_SSPIF, "SSPIF must assert");
}

/// SSPSTAT.BF (Buffer Full) is initially 0 after POR (SSPSTAT
/// POR = `0000 0000`).
#[test]
fn sspstat_bf_starts_clear_after_por() {
    let core = run_mssp_demo(0x77, 1);
    let stat = core.memory.read_raw(Address::from_raw(SSPSTAT_ADDR));
    assert_eq!(stat, 0);
}

/// SSPADD persists at the firmware-set value.
#[test]
fn sspadd_persists() {
    let core = run_mssp_demo(0x77, 6);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(SSPADD_ADDR)),
        0x77,
    );
}

#[test]
fn unsupported_modes_and_general_call_are_inert_for_fid10() {
    // §11c FID-10: SPI mode, I2C slave/10-bit addressing,
    // and General Call are explicit DLCP out-of-scope modes.
    // Per DS39632E/DS40001303H MSSP mode tables, those SSPM/
    // GCEN settings are not the DLCP I2C-master path, so this
    // model leaves them inert: no I2C-master state, bus event,
    // or SSPIF is produced accidentally.
    let mut core = Core::new(Variant::Pic18F2455);

    core.memory.write_raw(
        Address::from_raw(SSPCON1_ADDR),
        SSPCON1_SSPEN | SSPM_SPI_MASTER,
    );
    core.memory
        .write_raw(Address::from_raw(SSPCON2_ADDR), SSPCON2_SEN);
    core.peripherals
        .mssp
        .on_sfr_write(SSPCON2_ADDR, SSPCON2_SEN, &mut core.memory);
    core.peripherals.tick_tcy(100, &mut core.memory);
    assert_eq!(core.memory.read_raw(Address::from_raw(SSPCON2_ADDR)), 0);
    assert_eq!(core.memory.read_raw(Address::from_raw(PIR1_ADDR)) & PIR1_SSPIF, 0);
    assert_eq!(core.peripherals.mssp.take_last_bus_event(), None);

    core.memory.write_raw(
        Address::from_raw(SSPCON1_ADDR),
        SSPCON1_SSPEN | SSPM_I2C_SLAVE_10BIT,
    );
    core.memory
        .write_raw(Address::from_raw(SSPCON2_ADDR), SSPCON2_SEN);
    core.peripherals
        .mssp
        .on_sfr_write(SSPCON2_ADDR, SSPCON2_SEN, &mut core.memory);
    core.peripherals.tick_tcy(100, &mut core.memory);
    assert_eq!(core.memory.read_raw(Address::from_raw(SSPCON2_ADDR)), 0);
    assert_eq!(core.memory.read_raw(Address::from_raw(PIR1_ADDR)) & PIR1_SSPIF, 0);
    assert_eq!(core.peripherals.mssp.take_last_bus_event(), None);

    core.memory.write_raw(
        Address::from_raw(SSPCON1_ADDR),
        SSPCON1_SSPEN | SSPM_I2C_MASTER,
    );
    core.memory
        .write_raw(Address::from_raw(SSPCON2_ADDR), SSPCON2_GCEN);
    core.peripherals
        .mssp
        .on_sfr_write(SSPCON2_ADDR, SSPCON2_GCEN, &mut core.memory);
    core.peripherals.tick_tcy(100, &mut core.memory);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(SSPCON2_ADDR)) & SSPCON2_GCEN,
        SSPCON2_GCEN,
        "GCEN persists as an SFR bit but does not schedule a master transfer"
    );
    assert_eq!(core.memory.read_raw(Address::from_raw(PIR1_ADDR)) & PIR1_SSPIF, 0);

    core.memory
        .write_raw(Address::from_raw(SSPBUF_ADDR), 0xA5);
    core.peripherals
        .mssp
        .on_sfr_write(SSPBUF_ADDR, 0xA5, &mut core.memory);
    core.peripherals.tick_tcy(100, &mut core.memory);
    assert_eq!(
        core.peripherals.mssp.take_last_bus_event(),
        Some(I2cBusEvent::TxByte(0xA5)),
        "DLCP I2C-master SSPBUF path remains covered"
    );
}

#[test]
fn clock_stretch_collision_and_lines_cover_fid10() {
    // §11c FID-10: clock stretching, bus collision, and
    // SDA/SCL line state are firmware-visible MSSP behaviors.
    // The simulator exposes deterministic hooks until FID-14's
    // pin network owns real line propagation.
    let mut core = Core::new(Variant::Pic18F2455);
    core.memory.write_raw(Address::from_raw(SSPADD_ADDR), 3);
    core.memory.write_raw(
        Address::from_raw(SSPCON1_ADDR),
        SSPCON1_SSPEN | SSPM_I2C_MASTER,
    );

    core.peripherals.mssp.set_clock_stretch(5, 1);
    core.memory
        .write_raw(Address::from_raw(SSPCON2_ADDR), SSPCON2_SEN);
    core.peripherals
        .mssp
        .on_sfr_write(SSPCON2_ADDR, SSPCON2_SEN, &mut core.memory);
    core.peripherals.tick_tcy(4, &mut core.memory);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(SSPCON2_ADDR)) & SSPCON2_SEN,
        SSPCON2_SEN,
        "clock stretch keeps SEN pending beyond the nominal SCL period"
    );
    assert_eq!(core.memory.read_raw(Address::from_raw(PIR1_ADDR)) & PIR1_SSPIF, 0);
    core.peripherals.tick_tcy(5, &mut core.memory);
    assert_eq!(core.memory.read_raw(Address::from_raw(SSPCON2_ADDR)) & SSPCON2_SEN, 0);
    assert_eq!(core.memory.read_raw(Address::from_raw(PIR1_ADDR)) & PIR1_SSPIF, PIR1_SSPIF);
    let lines = core.peripherals.mssp.lines();
    assert!(lines.scl_high);
    assert!(!lines.sda_high, "START leaves SDA low while SCL is high");
    assert_eq!(
        core.peripherals.mssp.take_last_bus_event(),
        Some(I2cBusEvent::Start)
    );

    core.memory.write_raw(Address::from_raw(PIR1_ADDR), 0);
    core.memory
        .write_raw(Address::from_raw(SSPCON2_ADDR), SSPCON2_PEN);
    core.peripherals
        .mssp
        .on_sfr_write(SSPCON2_ADDR, SSPCON2_PEN, &mut core.memory);
    core.peripherals.tick_tcy(4, &mut core.memory);
    let lines = core.peripherals.mssp.lines();
    assert!(lines.scl_high);
    assert!(lines.sda_high, "STOP releases both I2C lines high");

    core.memory
        .write_raw(Address::from_raw(SSPCON2_ADDR), SSPCON2_RSEN);
    core.peripherals
        .mssp
        .on_sfr_write(SSPCON2_ADDR, SSPCON2_RSEN, &mut core.memory);
    core.peripherals
        .mssp
        .inject_bus_collision(&mut core.memory);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(PIR2_ADDR)) & PIR2_BCLIF,
        PIR2_BCLIF,
        "explicit collision hook asserts PIR2.BCLIF"
    );
    assert_eq!(
        core.memory.read_raw(Address::from_raw(SSPCON2_ADDR))
            & (SSPCON2_SEN | SSPCON2_RSEN | SSPCON2_PEN),
        0,
        "collision leaves a recoverable idle trigger state"
    );
}
