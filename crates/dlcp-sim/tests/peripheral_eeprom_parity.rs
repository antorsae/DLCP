//! P2.5 EEPROM peripheral parity gate.
//!
//! Phase-2 single-core scope: full unlock-sequence enforcement,
//! 12 000 Tcy post-write delay (datasheet 2..5 ms typical),
//! WR auto-clear + EEIF assertion on completion, RD path
//! self-clear.  Bit-exact EEPROM-after-write parity against
//! gpsim is intentionally NOT the goal -- gpsim writes are
//! instantaneous (a known fidelity gap; see eeprom.rs
//! docstring).

use dlcp_sim::core::Core;
use dlcp_sim::exec::step;
use dlcp_sim::memory::{Address, Variant};
use dlcp_sim::peripherals::eeprom::{
    EEADR_ADDR, EECON1_ADDR, EECON2_ADDR, EEDATA_ADDR, PIR2_ADDR,
};
use dlcp_sim::reset::{ResetSource, apply_reset};
use dlcp_sim::stack::Stack;

const EECON1_WREN: u8 = 1 << 2;
const EECON1_WR: u8 = 1 << 1;
const EECON1_WRERR: u8 = 1 << 3;
const PIR2_EEIF: u8 = 1 << 4;

fn encode_movlw(k: u8) -> [u8; 2] {
    [k, 0x0E]
}
fn encode_movwf(f: u8) -> [u8; 2] {
    let word = 0x6E00u16 | (f as u16);
    [word as u8, (word >> 8) as u8]
}

/// Build a flash that performs the full firmware idiom for an
/// EEPROM write:
///   MOVLW addr; MOVWF EEADR
///   MOVLW data; MOVWF EEDATA
///   MOVLW 0x55; MOVWF EECON2
///   MOVLW 0xAA; MOVWF EECON2
///   BSF EECON1, WR  -- approximated by MOVWF EECON1 with WR|WREN
///   BRA -1
fn build_eeprom_write_demo_flash(addr: u8, data: u8) -> Vec<u8> {
    let mut flash = vec![0u8; 32 * 1024];
    let prog: &[(u32, [u8; 2])] = &[
        (0x0000, encode_movlw(addr)),
        (0x0002, encode_movwf(0xA9)), // EEADR @ 0xFA9
        (0x0004, encode_movlw(data)),
        (0x0006, encode_movwf(0xA8)), // EEDATA @ 0xFA8
        (0x0008, encode_movlw(0x55)),
        (0x000A, encode_movwf(0xA7)), // EECON2 @ 0xFA7
        (0x000C, encode_movlw(0xAA)),
        (0x000E, encode_movwf(0xA7)), // EECON2 @ 0xFA7
        (0x0010, encode_movlw(EECON1_WREN | EECON1_WR)),
        (0x0012, encode_movwf(0xA6)), // EECON1 @ 0xFA6
        (0x0014, [0xFF, 0xD7]),       // BRA -1
    ];
    for (a, bytes) in prog {
        flash[*a as usize] = bytes[0];
        flash[*a as usize + 1] = bytes[1];
    }
    flash
}

fn run_eeprom_demo(addr: u8, data: u8, cycle_target: u64) -> Core {
    let mut core = Core::new(Variant::Pic18F25K20);
    core.flash_mut().copy_from_slice(&build_eeprom_write_demo_flash(addr, data));
    let mut stack = Stack::new();
    apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
    let mut total: u64 = 0;
    while total < cycle_target {
        let cycles = step(&mut core, &mut stack)
            .expect("EEPROM demo executes cleanly");
        total += cycles as u64;
    }
    core
}

#[test]
fn unlocked_write_completes_after_12000_tcy() {
    // 11 setup instructions + 12000 Tcy post-write +
    // BRA-loop slack.  Run 13 000 Tcy total.
    let core = run_eeprom_demo(0x42, 0xCD, 13_000);
    let con1 = core.memory.read_raw(Address::from_raw(EECON1_ADDR));
    assert_eq!(con1 & EECON1_WR, 0, "WR must auto-clear post-write");
    let pir2 = core.memory.read_raw(Address::from_raw(PIR2_ADDR));
    assert_eq!(pir2 & PIR2_EEIF, PIR2_EEIF, "EEIF must assert post-write");
    assert_eq!(core.peripherals.eeprom.get_byte(0x42), 0xCD);
}

#[test]
fn wr_still_set_mid_post_write_window() {
    // Run 100 Tcy (well past setup, well before 12 000-Tcy
    // completion).
    let core = run_eeprom_demo(0x42, 0xCD, 100);
    let con1 = core.memory.read_raw(Address::from_raw(EECON1_ADDR));
    assert_eq!(con1 & EECON1_WR, EECON1_WR, "WR must remain set");
    let pir2 = core.memory.read_raw(Address::from_raw(PIR2_ADDR));
    assert_eq!(pir2 & PIR2_EEIF, 0, "EEIF must NOT yet be set");
    assert_eq!(
        core.peripherals.eeprom.get_byte(0x42),
        0,
        "EEPROM byte not yet committed"
    );
}

/// Skip the 0xAA write to test the WRERR path.  Build a
/// flash that does 0x55 -> EECON2; 0x99 (wrong) -> EECON2;
/// then WR.
#[test]
fn unlock_sequence_violation_sets_wrerr() {
    let mut flash = vec![0u8; 32 * 1024];
    let prog: &[(u32, [u8; 2])] = &[
        (0x0000, encode_movlw(0x33)),
        (0x0002, encode_movwf(0xA9)), // EEADR
        (0x0004, encode_movlw(0xCC)),
        (0x0006, encode_movwf(0xA8)), // EEDATA
        (0x0008, encode_movlw(0x55)),
        (0x000A, encode_movwf(0xA7)), // EECON2 = 0x55
        (0x000C, encode_movlw(0x99)),
        (0x000E, encode_movwf(0xA7)), // EECON2 = 0x99 (BAD)
        (0x0010, encode_movlw(EECON1_WREN | EECON1_WR)),
        (0x0012, encode_movwf(0xA6)), // EECON1 = WREN|WR
        (0x0014, [0xFF, 0xD7]),
    ];
    for (a, bytes) in prog {
        flash[*a as usize] = bytes[0];
        flash[*a as usize + 1] = bytes[1];
    }
    let mut core = Core::new(Variant::Pic18F25K20);
    core.flash_mut().copy_from_slice(&flash);
    let mut stack = Stack::new();
    apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
    let mut total: u64 = 0;
    while total < 100 {
        let cycles = step(&mut core, &mut stack).unwrap();
        total += cycles as u64;
    }
    let con1 = core.memory.read_raw(Address::from_raw(EECON1_ADDR));
    assert_eq!(
        con1 & EECON1_WRERR,
        EECON1_WRERR,
        "WRERR must assert on bad unlock"
    );
    assert_eq!(
        core.peripherals.eeprom.get_byte(0x33),
        0,
        "EEPROM unchanged on bad unlock"
    );
}

#[test]
fn write_address_data_persist_across_subsequent_eeadr_changes() {
    // Build a flash that sets EEADR=0x10/EEDATA=0xAA, does the
    // unlock + WR, then immediately overwrites EEADR=0x20.
    // The pending write should still commit to 0x10 (latched
    // at WR-trigger time).
    let mut flash = vec![0u8; 32 * 1024];
    let prog: &[(u32, [u8; 2])] = &[
        (0x0000, encode_movlw(0x10)),
        (0x0002, encode_movwf(0xA9)), // EEADR=0x10
        (0x0004, encode_movlw(0xAA)),
        (0x0006, encode_movwf(0xA8)), // EEDATA=0xAA
        (0x0008, encode_movlw(0x55)),
        (0x000A, encode_movwf(0xA7)), // EECON2=0x55
        (0x000C, encode_movlw(0xAA)),
        (0x000E, encode_movwf(0xA7)), // EECON2=0xAA
        (0x0010, encode_movlw(EECON1_WREN | EECON1_WR)),
        (0x0012, encode_movwf(0xA6)), // EECON1=WREN|WR
        // Mid-pending: change EEADR to 0x20.
        (0x0014, encode_movlw(0x20)),
        (0x0016, encode_movwf(0xA9)),
        (0x0018, [0xFF, 0xD7]),
    ];
    for (a, bytes) in prog {
        flash[*a as usize] = bytes[0];
        flash[*a as usize + 1] = bytes[1];
    }
    let mut core = Core::new(Variant::Pic18F25K20);
    core.flash_mut().copy_from_slice(&flash);
    let mut stack = Stack::new();
    apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
    let mut total: u64 = 0;
    while total < 13_000 {
        let cycles = step(&mut core, &mut stack).unwrap();
        total += cycles as u64;
    }
    assert_eq!(
        core.peripherals.eeprom.get_byte(0x10),
        0xAA,
        "write committed to latched address 0x10"
    );
    assert_eq!(
        core.peripherals.eeprom.get_byte(0x20),
        0,
        "no spurious write at 0x20"
    );
}
