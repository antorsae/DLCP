//! Phase-3.5 multicore parity scaffold.
//!
//! Spec target: reproduce `tests/sim/test_v171_v31_chain.py`
//! end-to-end with bit-exact TX byte streams + LCD raster
//! against ground truth captured from gpsim.
//!
//! ## Sub-task progression
//!
//! * P3.5 part-1 (commit f4c9a70): chain dispatch wires
//!   `exec::step` for `CoreInstructionComplete` events and
//!   reschedules the next event at the drifted-tick boundary.
//! * P3.5 part-2 (commit d916ffa, with same-tick race fixed
//!   in 8938eda): EUSART completed-TX bytes propagate
//!   directly to wired peer cores' RCREGs.
//! * **P3.5 part-3 (this file)**: smoke-test that the
//!   chain can load V1.71 + V3.1 hex images, wire the
//!   bidirectional UART, apply POR, and step for a small
//!   bounded number of universal ticks WITHOUT panicking.
//!   No bit-exact comparison yet -- ground-truth capture +
//!   diff lands in P3.5 part-4+.
//!
//! ## Why a smoke test first
//!
//! P1.8d already validates V1.71 K20 reset-through-init for
//! 10 Tcy bit-exact against gpsim, but that's a *single-
//! core* gate.  P3.5 part-3 is the first time the chain
//! dispatcher runs real shipped firmware on both sides
//! simultaneously with cross-core UART wiring active.
//! Peripheral-fidelity gaps (Timer3 RD16 buffer,
//! BAUDCON/SPBRGH/SPBRG baud math, MSSP I²C bus-clear, etc.)
//! and untested SFR-write side effects can surface as
//! unhandled-opcode `ExecError`s, panics in
//! `Peripherals::on_sfr_write`, or infinite loops.  Bound
//! the step count so a regression shows up as a fast test
//! failure (one panicked step) instead of a long hang.

use std::path::PathBuf;

use dlcp_sim::chain::Chain;
use dlcp_sim::core::Core;
use dlcp_sim::hex::HexImage;
use dlcp_sim::memory::Variant;
use dlcp_sim::pinnet::{default_rx_pin, default_tx_pin};
use dlcp_sim::reset::ResetSource;

/// Find the repo root by walking up from CARGO_MANIFEST_DIR
/// (`crates/dlcp-sim`) two levels.  Mirrors `isa_parity.rs`'s
/// `repo_root()` helper.
fn repo_root() -> PathBuf {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir
        .parent()
        .and_then(|p| p.parent())
        .expect("CARGO_MANIFEST_DIR has at least 2 parents")
        .to_path_buf()
}

fn v171_control_hex_path() -> PathBuf {
    repo_root().join("firmware/patched/releases/DLCP_Control_V1.71.hex")
}

fn v31_main_hex_path() -> PathBuf {
    repo_root().join("firmware/patched/releases/DLCP_Firmware_V3.1.hex")
}

/// Load a hex file into a fresh core of the given variant.
/// Mirrors `isa_parity.rs::run_to_cycle`'s setup minus the
/// step loop: copies flash, initialises EEPROM contents from
/// the hex image, applies POR.
fn build_core_from_hex(variant: Variant, image: &HexImage) -> Core {
    let mut core = Core::new(variant);
    core.flash_mut().copy_from_slice(&*image.flash);
    // Seed EEPROM bytes from the hex image so V1.71's preset
    // bank reads (EEPROM 0x74 = preset slot, etc.) see real
    // values rather than the all-0xFF erased state.  The hex
    // EEPROM window is 256 bytes; copy the full slice.
    for (addr, &byte) in image.eeprom.iter().enumerate() {
        if byte != 0xFF {
            // Skip 0xFF (erased) bytes so the EEPROM struct's
            // own POR fill (also 0xFF) is preserved -- no-op,
            // but explicit-skip keeps the code self-documenting.
            core.peripherals
                .eeprom
                .set_byte(addr as u8, byte);
        }
    }
    core
}

#[test]
fn chain_loads_v171_and_v31_hex() {
    // Sanity check that the hex files exist and parse before
    // we try to build a chain around them.
    let v171_path = v171_control_hex_path();
    let v31_path = v31_main_hex_path();
    assert!(
        v171_path.exists(),
        "V1.71 CONTROL hex not at {}",
        v171_path.display()
    );
    assert!(
        v31_path.exists(),
        "V3.1 MAIN hex not at {}",
        v31_path.display()
    );
    let v171 = HexImage::from_hex_path(&v171_path).expect("V1.71 hex parses");
    let v31 = HexImage::from_hex_path(&v31_path).expect("V3.1 hex parses");
    // V1.71 (K20 CONTROL): reset vector at 0x0000 is real
    // (`GOTO 0x7800` to the Microchip USB bootloader).
    assert_ne!(v171.flash[0], 0xFF, "V1.71 reset vector empty");
    // V3.1 (2455 MAIN): main image starts at 0x1000 because
    // the 2455 USB bootloader owns 0x0000..0x0FFF -- the hex
    // file does NOT include the bootloader, so flash[0..0x1000]
    // is the erased default (0xFF) and flash[0x1000] is the
    // first byte of the main firmware GOTO.
    assert_eq!(v31.flash[0], 0xFF, "V3.1 reset window must be erased (bootloader-owned)");
    assert_ne!(v31.flash[0x1000], 0xFF, "V3.1 main entry at 0x1000 empty");
}

#[test]
fn chain_with_v171_and_v31_steps_without_panic() {
    let v171 = HexImage::from_hex_path(v171_control_hex_path())
        .expect("V1.71 hex parses");
    let v31 = HexImage::from_hex_path(v31_main_hex_path())
        .expect("V3.1 hex parses");

    let control = build_core_from_hex(Variant::Pic18F25K20, &v171);
    let main = build_core_from_hex(Variant::Pic18F2455, &v31);

    let mut chain = Chain::new();
    let i_control = chain.push_core(control);
    let i_main = chain.push_core(main);

    // Bidirectional UART coupling: CONTROL TX (RC6) → MAIN RX
    // (RC7), and MAIN TX (RC6) → CONTROL RX (RC7).  Default
    // pin constants from `pinnet::default_{tx,rx}_pin` match
    // the PIC18 EUSART TX/RX assignment.
    chain.couple_uart(i_control, default_tx_pin(), i_main, default_rx_pin());
    chain.couple_uart(i_main, default_tx_pin(), i_control, default_rx_pin());

    chain.apply_reset_all(ResetSource::PowerOn);
    // Same-PSU boot: CONTROL and MAIN come up together.
    chain.schedule_initial_steps(&[0, 0]);

    // Step a small bounded budget.  Picking 100 universal
    // ticks is conservative: K20 advances 100/16 ≈ 6 Tcy
    // (well within P1.8d's 10-Tcy validated reset-through-init
    // window), and 2455 advances 100/12 ≈ 8 Tcy (no
    // pre-validated bound -- this test is the first multi-
    // core integration run, so a small budget keeps the
    // failure mode "panic on first divergent instruction"
    // fast).  Subsequent sub-tasks (P3.5 part-4+) will bump
    // this budget once peripheral fidelity gaps are closed
    // and ground-truth comparison lands.
    chain.step_ticks(100);

    // Both cores must have made forward progress (cycle
    // counter strictly positive).
    let control_cycles = chain.cores[i_control].cycles();
    let main_cycles = chain.cores[i_main].cycles();
    assert!(
        control_cycles > 0,
        "CONTROL did not advance under chain dispatch"
    );
    assert!(
        main_cycles > 0,
        "MAIN did not advance under chain dispatch"
    );

    // Universal clock advanced to the step target.
    assert_eq!(
        chain.current_tick, 100,
        "chain current_tick must equal step target"
    );
}
