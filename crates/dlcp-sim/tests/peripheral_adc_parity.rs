//! P2.4 ADC peripheral parity gate.
//!
//! Phase-2 single-core scope: SFR-write reactivity, GO/DONE
//! trigger gated on ADON, conversion completion clearing
//! GO/DONE + asserting ADIF, and ADRESH:ADRESL load with
//! the configured AN0 sample value (test-injected).  Bit-
//! level Tcy timing against gpsim's exact Tacq/Tconv math
//! is Phase-4 dual-run scope.
//!
//! V3.2 boot path uses 0x0236 / 0x0229 / 0x0228 thresholds
//! (per `tests/sim/test_main_gpsim_an0_boot.py`).  The
//! integration test below pins those.

use dlcp_sim::core::Core;
use dlcp_sim::exec::step;
use dlcp_sim::memory::{Address, Variant};
use dlcp_sim::peripherals::adc::{ADCON0_ADDR, ADCON2_ADDR, ADRESH_ADDR, ADRESL_ADDR, PIR1_ADDR};
use dlcp_sim::reset::{ResetSource, apply_reset};
use dlcp_sim::stack::Stack;

const ADCON0_GODONE: u8 = 1 << 1;
const ADCON0_ADON: u8 = 1 << 0;
const ADCON2_ADFM: u8 = 1 << 7;
const PIR1_ADIF: u8 = 1 << 6;

fn encode_movlw(k: u8) -> [u8; 2] {
    [k, 0x0E]
}
fn encode_movwf(f: u8) -> [u8; 2] {
    let word = 0x6E00u16 | (f as u16);
    [word as u8, (word >> 8) as u8]
}

/// Build a flash that:
///   1. sets ADCON2.ADFM=1 (right-justified)
///   2. enables ADC + sets GO/DONE to trigger conversion
///   3. loops on BRA -1
fn build_adc_demo_flash() -> Vec<u8> {
    let mut flash = vec![0u8; 32 * 1024];
    let prog: &[(u32, [u8; 2])] = &[
        (0x0000, encode_movlw(ADCON2_ADFM)),
        (0x0002, encode_movwf(0xC0)), // ADCON2 @ 0xFC0
        (0x0004, encode_movlw(ADCON0_GODONE | ADCON0_ADON)),
        (0x0006, encode_movwf(0xC2)), // ADCON0 @ 0xFC2
        (0x0008, [0xFF, 0xD7]),       // BRA -1
    ];
    for (addr, bytes) in prog {
        flash[*addr as usize] = bytes[0];
        flash[*addr as usize + 1] = bytes[1];
    }
    flash
}

fn run_adc_demo(an0: u16, cycle_target: u64) -> Core {
    let mut core = Core::new(Variant::Pic18F2455);
    core.flash_mut().copy_from_slice(&build_adc_demo_flash());
    let mut stack = Stack::new();
    apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
    core.peripherals.adc.set_an0_sample(an0);
    let mut total: u64 = 0;
    while total < cycle_target {
        let cycles = step(&mut core, &mut stack)
            .expect("ADC demo executes cleanly");
        total += cycles as u64;
    }
    core
}

/// V3.2 boot: AN0 reads 0x0236 (just above the standby
/// threshold).  After the firmware-driven conversion
/// completes, ADRESH:ADRESL must hold the right-justified
/// 0x0236 value; ADIF asserts; GO/DONE auto-clears.
#[test]
fn an0_0x0236_loads_correct_adresh_adresl() {
    // 4 setup instructions + 12 Tcy conversion + 1 BRA tail
    // = ~20 Tcy.  Run a comfortable 50.
    let core = run_adc_demo(0x0236, 50);
    let con0 = core.memory.read_raw(Address::from_raw(ADCON0_ADDR));
    assert_eq!(con0 & ADCON0_GODONE, 0, "GO/DONE must auto-clear");
    assert_eq!(con0 & ADCON0_ADON, ADCON0_ADON, "ADON preserved");
    let pir1 = core.memory.read_raw(Address::from_raw(PIR1_ADDR));
    assert_eq!(pir1 & PIR1_ADIF, PIR1_ADIF, "ADIF must assert");
    assert_eq!(
        core.memory.read_raw(Address::from_raw(ADRESH_ADDR)),
        0x02
    );
    assert_eq!(
        core.memory.read_raw(Address::from_raw(ADRESL_ADDR)),
        0x36
    );
}

/// AN0 = 0x0229 (low hysteresis).
#[test]
fn an0_0x0229_loads_correct_adresh_adresl() {
    let core = run_adc_demo(0x0229, 50);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(ADRESH_ADDR)),
        0x02
    );
    assert_eq!(
        core.memory.read_raw(Address::from_raw(ADRESL_ADDR)),
        0x29
    );
}

/// Mid-conversion the GO/DONE bit is still set.
#[test]
fn godone_still_set_mid_conversion() {
    // Run just past setup (4 Tcy) but before conversion
    // completes (4 + 12 = 16).  At total=8 we're 4 Tcy
    // into the 12-Tcy conversion window.
    let core = run_adc_demo(0x0100, 8);
    let con0 = core.memory.read_raw(Address::from_raw(ADCON0_ADDR));
    assert_eq!(
        con0 & ADCON0_GODONE,
        ADCON0_GODONE,
        "GO/DONE must remain set mid-conversion"
    );
}

/// ADIF stays low until conversion completes.
#[test]
fn adif_low_until_conversion_completes() {
    let core = run_adc_demo(0x0100, 8);
    let pir1 = core.memory.read_raw(Address::from_raw(PIR1_ADDR));
    assert_eq!(pir1 & PIR1_ADIF, 0);
}
