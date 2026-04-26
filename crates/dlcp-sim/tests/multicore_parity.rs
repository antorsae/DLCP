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
///
/// The 2455 V3.x main image leaves the bootloader window
/// (`flash[0..0x1000]`) erased.  On real silicon the
/// Microchip USB bootloader at 0x0000 jumps to the app
/// entry at 0x1000 when not in update mode; the simulator
/// has no bootloader image, so the caller can ask us to
/// bake a `GOTO 0x1000` into `flash[0..4]` to mimic that
/// jump and get the V3.1 app actually executing.
fn build_core_from_hex(
    variant: Variant,
    image: &HexImage,
    bake_goto_app_entry: Option<u32>,
) -> Core {
    let mut core = Core::new(variant);
    core.flash_mut().copy_from_slice(&*image.flash);

    if let Some(app_entry_byte_addr) = bake_goto_app_entry {
        // PIC18 GOTO encoding (DS39632E §26 / DS41303 §25):
        //   word1 = 1110 1111 k<7:0>     (high byte 0xEF, low = k<7:0>)
        //   word2 = 1111 0000 k<19:8>    (high byte 0xF0 | k<19:16>,
        //                                  low byte = k<15:8>)
        // `k` is the **word** address (target_byte_addr / 2).  PCL bit 0
        // is hard-wired to 0 on PIC18, so app-entry addresses are even.
        assert!(
            app_entry_byte_addr & 1 == 0,
            "GOTO target byte address must be even"
        );
        let k_word = app_entry_byte_addr >> 1;
        assert!(
            k_word <= 0x000F_FFFF,
            "GOTO target out of 21-bit PC range"
        );
        let word1_lo = (k_word & 0xFF) as u8;
        let word1_hi = 0xEFu8;
        let word2_lo = ((k_word >> 8) & 0xFF) as u8;
        let word2_hi = 0xF0u8 | (((k_word >> 16) & 0x0F) as u8);
        let flash = core.flash_mut();
        flash[0] = word1_lo;
        flash[1] = word1_hi;
        flash[2] = word2_lo;
        flash[3] = word2_hi;
    }

    // Seed EEPROM bytes from the hex image.  The EEPROM
    // peripheral's `Default` initialises storage to 0x00
    // (not 0xFF), so we must copy EVERY byte -- including
    // 0xFF "erased" bytes -- to faithfully reflect the
    // hex's contents on the simulator side.  This matters
    // because firmware reads of erased EEPROM cells
    // expect 0xFF, not 0x00, and the data-init logic on
    // V1.71/V3.x treats 0xFF as the "uninitialized" sentinel.
    for (addr, &byte) in image.eeprom.iter().enumerate() {
        core.peripherals
            .eeprom
            .set_byte(addr as u8, byte);
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

    // V1.71 (K20 CONTROL): reset vector at 0x0000 is the
    // shipped `GOTO 0x7800` (jump to the Microchip USB
    // bootloader at 0x7800).  Encoding from DS40001303H §26:
    //   word1 = 0xEF00 (low byte k<7:0> = 0x00)
    //   word2 = 0xF03C (low byte k<15:8> = 0x3C, k<19:16> = 0)
    // -> word addr 0x3C00 = byte addr 0x7800.  Bytes in flash:
    //   [0x00, 0xEF, 0x3C, 0xF0]
    assert_eq!(
        &v171.flash[0..4],
        &[0x00, 0xEF, 0x3C, 0xF0],
        "V1.71 reset vector must be GOTO 0x7800 (bootloader entry)"
    );

    // V3.1 (2455 MAIN): main image starts at 0x1000 because
    // the 2455 USB bootloader owns 0x0000..0x0FFF -- the hex
    // file does NOT include the bootloader, so flash[0..0x1000]
    // is the erased default (0xFF) and flash[0x1000] is the
    // first byte of the main firmware's entry GOTO.
    assert_eq!(
        v31.flash[0], 0xFF,
        "V3.1 reset window must be erased (bootloader-owned)"
    );
    // First record at 0x1000 is `0AEF08F0` -- that's
    // `GOTO 0x1014` (k_word = 0x080A → byte addr 0x1014, the
    // shipped V3.x main code's entry trampoline).
    assert_eq!(
        &v31.flash[0x1000..0x1004],
        &[0x0A, 0xEF, 0x08, 0xF0],
        "V3.1 main entry at 0x1000 must be GOTO 0x1014 (shipped)"
    );
}

#[test]
fn chain_with_v171_and_v31_steps_without_panic() {
    let v171 = HexImage::from_hex_path(v171_control_hex_path())
        .expect("V1.71 hex parses");
    let v31 = HexImage::from_hex_path(v31_main_hex_path())
        .expect("V3.1 hex parses");

    // CONTROL has its own reset vector at 0x0000; no need to
    // bake an entry-point GOTO.  MAIN's hex leaves
    // flash[0..0x1000] erased (the 2455 USB bootloader window
    // is not in the shipped hex), so we bake `GOTO 0x1000`
    // into MAIN's reset vector to mimic what the bootloader
    // does on real silicon when not in update mode.
    let control = build_core_from_hex(Variant::Pic18F25K20, &v171, None);
    let main = build_core_from_hex(Variant::Pic18F2455, &v31, Some(0x1000));

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

    // Both cores made forward progress (cycle counter
    // strictly positive).
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

    // MAIN ran past BOTH trampolines: the baked GOTO 0x1000
    // at flash[0..4], and the shipped `GOTO 0x1014` at
    // flash[0x1000..0x1004].  PC must be strictly past
    // 0x1014 so the test catches regressions where execution
    // stalls at either trampoline target -- a `>= 0x1000`
    // bound would let "GOTO fired once but second GOTO
    // didn't" silently pass.  At 100 universal ticks ≈ 8 Tcy
    // on the 2455, two 2-Tcy GOTOs consume 4 Tcy and leave
    // ~4 Tcy for V3.1's real entry code, which advances PC
    // a few more bytes past 0x1014.
    let main_pc = chain.cores[i_main].pc();
    assert!(
        main_pc > 0x1014,
        "MAIN PC must be strictly past V3.1 entry trampoline (> 0x1014), got 0x{:04X}",
        main_pc
    );

    // CONTROL's shipped reset vector points at the Microchip
    // USB bootloader (0x7800), and the V1.71 hex doesn't
    // include the bootloader itself.  Without the bootloader,
    // CONTROL runs erased-flash NOPs from 0x7800 onward in
    // this scaffold -- i.e. the cycle-progress assertion
    // above proves the chain dispatcher works, but does NOT
    // prove that V1.71 application code is executing.
    // P3.5 part-4+ will either load the bootloader hex
    // alongside V1.71 or bake a synthetic GOTO past the
    // V1.71 vector block to reach the app entry directly.

    // Universal clock advanced to the step target.
    assert_eq!(
        chain.current_tick, 100,
        "chain current_tick must equal step target"
    );
}
