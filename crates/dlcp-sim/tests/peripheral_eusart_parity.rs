//! P2.1 EUSART peripheral parity gate.
//!
//! Phase 2 scope is single-core local: the EUSART produces
//! correct TXSTA.TRMT / PIR1.TXIF transitions in lock-step with
//! the executor's cycle counter, given a known firmware-style
//! TXREG-write sequence.  Bit-level comparison against gpsim's
//! UART byte stream lives in Phase 4 dual-run; here we validate
//! the state-machine invariants the firmware observes via SFR
//! polling.
//!
//! Tests in this file exercise the EUSART through the *real*
//! executor path (instructions writing through `write_addr_masked`)
//! rather than the unit-test path that pokes the peripheral
//! directly, to make sure the Core ↔ Peripherals plumbing is
//! correctly wired.

use dlcp_sim::core::Core;
use dlcp_sim::exec::step;
use dlcp_sim::memory::{Address, Variant};
use dlcp_sim::peripherals::eusart::{
    BAUDCON_ADDR, PIR1_ADDR, RCSTA_ADDR, SPBRG_ADDR, TXSTA_ADDR,
};
use dlcp_sim::reset::{ResetSource, apply_reset};
use dlcp_sim::stack::Stack;

const TXSTA_TRMT: u8 = 1 << 1;
const TXSTA_TXEN: u8 = 1 << 5;
const PIR1_TXIF: u8 = 1 << 4;
const RCSTA_SPEN: u8 = 1 << 7;

/// Encode a `MOVLW k` instruction (opcode `0x0E kk`).
fn encode_movlw(k: u8) -> [u8; 2] {
    // PIC18 instructions are little-endian in flash.
    [k, 0x0E]
}

/// Encode a `MOVWF f, A=0` (Access-bank) instruction
/// (opcode `0x6F ff` for a-bit=1; we want a=0 to address the
/// SFR window via Access-bank-high half).
fn encode_movwf(f: u8) -> [u8; 2] {
    // movwf f, a:  `0110 111a ffff ffff`
    // a=0 -> word = 0x6E00 | f
    let word = 0x6E00u16 | (f as u16);
    [word as u8, (word >> 8) as u8]
}

/// Build a small flash image that runs the V1.71 EUSART setup
/// (SPBRG=5; TXSTA = TXEN; RCSTA = SPEN; TXREG = 0x55) starting
/// at the reset vector, then loops on an unconditional branch.
fn build_eusart_demo_flash() -> Vec<u8> {
    let mut flash = vec![0u8; 32 * 1024];

    // Address layout starting at 0x0000 (reset vector):
    //   0x0000: MOVLW 0x05
    //   0x0002: MOVWF SPBRG  (0xFAF, access bank low byte = 0xAF)
    //   0x0004: MOVLW 0x20   (TXEN)
    //   0x0006: MOVWF TXSTA  (0xFAC, low byte = 0xAC)
    //   0x0008: MOVLW 0x80   (SPEN)
    //   0x000A: MOVWF RCSTA  (0xFAB, low byte = 0xAB)
    //   0x000C: MOVLW 0x40   (BAUDCON RCIDL=1 mirroring V1.71)
    //   0x000E: MOVWF BAUDCON (0xFB8, low byte = 0xB8)
    //   0x0010: MOVLW 0x55
    //   0x0012: MOVWF TXREG  (0xFAD, low byte = 0xAD)
    //   0x0014: BRA -2       (loop forever; opcode 0xD7FF)
    //
    // a=0 puts addresses 0x60..0xFF on the Access-bank-high half
    // mapped to SFRs 0xF60..0xFFF, which is exactly the EUSART
    // SFR cluster; we use the low byte directly.
    let program: &[(u32, [u8; 2])] = &[
        (0x0000, encode_movlw(0x05)),
        (0x0002, encode_movwf(0xAF)), // SPBRG
        (0x0004, encode_movlw(0x20)),
        (0x0006, encode_movwf(0xAC)), // TXSTA
        (0x0008, encode_movlw(0x80)),
        (0x000A, encode_movwf(0xAB)), // RCSTA
        (0x000C, encode_movlw(0x40)),
        (0x000E, encode_movwf(0xB8)), // BAUDCON
        (0x0010, encode_movlw(0x55)),
        (0x0012, encode_movwf(0xAD)), // TXREG
        // BRA -2 (offset = -2 instruction-words, encoded n = 0xFE):
        // opcode = 0xD000 | (0x07FF & -1)  -> 0xD7FF
        (0x0014, [0xFF, 0xD7]),
    ];
    for (addr, bytes) in program {
        flash[*addr as usize] = bytes[0];
        flash[*addr as usize + 1] = bytes[1];
    }
    flash
}

/// Run the demo program for `cycle_target` Tcy and return the
/// final state.
fn run_demo(cycle_target: u64) -> (Core, Stack) {
    let mut core = Core::new(Variant::Pic18F25K20);
    core.flash_mut().copy_from_slice(&build_eusart_demo_flash());
    let mut stack = Stack::new();
    apply_reset(&mut core, &mut stack, ResetSource::PowerOn);

    let mut total: u64 = 0;
    while total < cycle_target {
        let cycles = step(&mut core, &mut stack)
            .expect("demo program executes cleanly");
        total += cycles as u64;
    }
    (core, stack)
}

/// After ~12 instructions (each 1 Tcy), the firmware has finished
/// writing TXREG and TRMT must read 0.
#[test]
fn txreg_write_clears_trmt_via_executor() {
    // The TXREG write lands at instruction 11 (after 11 Tcy of
    // setup ops).  Run for 12 Tcy total to land just past the
    // TXREG write.
    let (core, _) = run_demo(12);
    let txsta = core.memory.read_raw(Address::from_raw(TXSTA_ADDR));
    let pir1 = core.memory.read_raw(Address::from_raw(PIR1_ADDR));
    assert_eq!(
        txsta & TXSTA_TRMT,
        0,
        "TRMT must be 0 immediately after TXREG write (TXSTA=0x{txsta:02X})"
    );
    assert_eq!(pir1 & PIR1_TXIF, 0, "TXIF must be 0 mid-frame");
    assert_eq!(
        txsta & TXSTA_TXEN,
        TXSTA_TXEN,
        "TXEN must remain 1 after a SW write that didn't touch it"
    );
}

/// After the full frame drains (10 bits × 384 Tcy/bit at SPBRG=5),
/// TRMT and TXIF must reassert.
#[test]
fn frame_completes_after_3840_tcy() {
    // 12 Tcy of setup + ~3840 Tcy frame + a BRA-loop slack.  Run
    // a comfortable 4_000 Tcy and check the post-frame state.
    let (core, _) = run_demo(4_000);
    let txsta = core.memory.read_raw(Address::from_raw(TXSTA_ADDR));
    let pir1 = core.memory.read_raw(Address::from_raw(PIR1_ADDR));
    assert_eq!(
        txsta & TXSTA_TRMT,
        TXSTA_TRMT,
        "TRMT must reassert post-frame (TXSTA=0x{txsta:02X})"
    );
    assert_eq!(
        pir1 & PIR1_TXIF,
        PIR1_TXIF,
        "TXIF must assert post-frame (PIR1=0x{pir1:02X})"
    );
}

/// Mid-frame the EUSART must keep TRMT cleared even as the BRA
/// loop ticks 1 Tcy at a time -- regression test for the
/// peripheral-tick hook firing on every instruction.
#[test]
fn trmt_stays_low_through_brz_loop_until_drained() {
    // 12 setup Tcy + 100 Tcy of mid-frame loop = 112 Tcy total,
    // well below the 12 + 3840 frame deadline.
    let (core, _) = run_demo(112);
    let txsta = core.memory.read_raw(Address::from_raw(TXSTA_ADDR));
    assert_eq!(
        txsta & TXSTA_TRMT,
        0,
        "TRMT must stay 0 throughout the in-flight frame (TXSTA=0x{txsta:02X})"
    );
}

/// Pre-TXREG-write the SFRs must reflect the firmware setup --
/// SPBRG=5, TXSTA=0x22 (TXEN | TRMT), RCSTA=SPEN, BAUDCON=0x40.
#[test]
fn pre_txreg_write_sfr_state_matches_firmware_setup() {
    // 9 Tcy = past the BAUDCON write (instruction 8 completes
    // at Tcy 8) but before the TXREG MOVWF (instruction 11).
    let (core, _) = run_demo(9);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(SPBRG_ADDR)),
        0x05,
        "SPBRG should be 5 (31250 baud at 3 MIPS Fcy)"
    );
    let txsta = core.memory.read_raw(Address::from_raw(TXSTA_ADDR));
    assert_eq!(
        txsta & (TXSTA_TXEN | TXSTA_TRMT),
        TXSTA_TXEN | TXSTA_TRMT,
        "TXSTA should have TXEN=1 (SW-written) and TRMT=1 (POR + idle)"
    );
    assert_eq!(
        core.memory.read_raw(Address::from_raw(RCSTA_ADDR)) & RCSTA_SPEN,
        RCSTA_SPEN,
        "RCSTA SPEN should be set"
    );
    assert_eq!(
        core.memory.read_raw(Address::from_raw(BAUDCON_ADDR)),
        0x40,
        "BAUDCON should match V1.71 setup (RCIDL=1)"
    );
}
