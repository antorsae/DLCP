//! Phase-3.5 multicore parity scaffold.
//!
//! Spec target: reproduce `tests/sim/test_v171_v31_chain.py`
//! end-to-end with bit-exact TX byte streams + LCD raster
//! against ground truth captured from gpsim.
//!
//! ## Sub-task progression
//!
//! * P3.5 part-1: chain dispatch wires `exec::step` for
//!   `CoreInstructionComplete` events and reschedules the
//!   next event at the drifted-tick boundary.
//! * P3.5 part-2: EUSART completed-TX bytes propagate
//!   directly to wired peer cores' RCREGs (same-tick race
//!   fixed in part-2 follow-up).
//! * P3.5 part-3: smoke-test that the chain can load V1.71
//!   + V3.1 hex images, wire bidirectional UART, apply POR,
//!   and step without panicking.
//! * P3.5 part-4: `Chain::uart_tx_history` recorder.
//! * P3.5 part-5: bumped budget to 10M, AN0 injection.
//! * P3.5 part-6: probe findings (Timer3 OK; I2C BF
//!   blocker).
//! * P3.5 part-7 (a/b/c): TAS3108 DSP I2C slave model +
//!   chain dispatch wiring + multicore_parity integration.
//! * P3.5 part-8 (a/b/c): `Chain::run_until` chunked-step
//!   harness + adoption + V3.1 TX-convergence probe.
//! * P3.5 part-9: IRQ vector dispatch in executor (closes
//!   task #28; unblocks V3.1 chain protocol convergence).
//! * P3.5 final-acceptance (minimum-viable): chain reaches
//!   first UART TX byte (~300 M ticks, ~2.7 s wall).
//! * P3.5 part-10+ (future): bit-exact TX byte stream and
//!   LCD raster comparison against gpsim ground truth --
//!   the strictly stronger spec contract per
//!   `docs/SIM_REWRITE_RUST_PROGRESS.md`.
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
use dlcp_sim::peripherals::tas3108::Tas3108;
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
    let mut main = build_core_from_hex(Variant::Pic18F2455, &v31, Some(0x1000));
    // V3.x MAIN early-boot reads AN0 in `adc_boot_gate` to
    // decide "is the unit plugged in?".  Without an injected
    // sample the ADC peripheral returns 0x0000 and MAIN parks
    // in a standby-poll loop forever.  Inject a value
    // comfortably above the V3.1/V3.2 boot-gate threshold
    // (0x0236 per `src/dlcp_fw/asm/dlcp_main_v31.asm::adc_boot_gate`;
    // 0x0228 is the runtime low-trip standby threshold, NOT
    // the boot gate) so MAIN clears the gate and continues
    // into chain protocol convergence.
    main.peripherals.adc.set_an0_sample(0x0300);

    let mut chain = Chain::new();
    let i_control = chain.push_core(control);
    let i_main = chain.push_core(main);

    // Bidirectional UART coupling: CONTROL TX (RC6) → MAIN RX
    // (RC7), and MAIN TX (RC6) → CONTROL RX (RC7).  Default
    // pin constants from `pinnet::default_{tx,rx}_pin` match
    // the PIC18 EUSART TX/RX assignment.
    chain.couple_uart(i_control, default_tx_pin(), i_main, default_rx_pin());
    chain.couple_uart(i_main, default_tx_pin(), i_control, default_rx_pin());

    // TAS3108 audio DSP wired to MAIN's MSSP I²C bus (CS0=0
    // -> slave addr 0x68/0x69 per `firmware/reference/tas3108.md`
    // Tbl 6-1).  Without this slave, MAIN's `dsp_ping`
    // (`firmware/patched/releases/DLCP_Firmware_V3.1.lst:7802`)
    // and `volume_dsp_write` (lst:7838) get NACK on every
    // master TX byte and the firmware spin-retries in
    // `wait_bf_clear_loop` (label at lst:7753, observed park
    // at lst:7757 = 0x4738).
    let i_tas3108 = chain.push_tas3108(Tas3108::default());
    chain.couple_tas3108(i_main, i_tas3108);

    chain.apply_reset_all(ResetSource::PowerOn);
    // Same-PSU boot: CONTROL and MAIN come up together.
    chain.schedule_initial_steps(&[0, 0]);

    // Use the chunked-step harness landed in P3.5 part-8a
    // to wait until the TAS3108 slave has ACKed at least
    // 1000 I2C bytes from MAIN (proving DSP init traffic
    // is flowing through the chain), with a 1 B-tick safety
    // ceiling.  Chunk size of 10 M ticks ≈ 70 ms wall
    // each; convergence on the prior fixed 500 M budget
    // observed ~6 k ACKs, so the first 1 k ACKs land much
    // sooner -- run_until's early exit shaves the wall-
    // clock cost.
    //
    // Why not wait for first UART TX byte instead?  V3.1's
    // chain protocol convergence (UART traffic to CONTROL)
    // requires several seconds more simulated time (>= 1 B
    // universal ticks = >= 7 s wall-clock per scaffolding
    // probes), still too slow for a unit-test-grade
    // assertion.  Locking in "DSP init began" is the
    // strongest predicate that still terminates quickly.
    chain.run_until(
        10_000_000,    // chunk_ticks: 10 M = ~70 ms wall
        1_000_000_000, // max_ticks:  1 B safety ceiling
        |c| c.tas3108_slaves[i_tas3108].bytes_acked >= 1000,
    );

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

    // MAIN ran past BOTH trampolines (the baked GOTO 0x1000
    // and the shipped GOTO 0x1014 at flash[0x1000..0x1004])
    // and into V3.1 application code.  By the time
    // `run_until` exits with `bytes_acked >= 1000`, MAIN's
    // PC has typically been observed at 0x428E
    // (mid-`flow_timer3_blocking_delay_449e` BRA, a normal
    // Timer3 overflow poll between DSP init bursts -- see
    // the longer comment above the `run_until` call for
    // context on why this is the chain-progress milestone).
    // Lock the progression in with a `> 0x4000` lower
    // bound.  If a future regression strands MAIN somewhere
    // earlier (back at 0x1014, in early-init bank-clear
    // loops, etc.) this assertion fires.
    let main_pc = chain.cores[i_main].pc();
    assert!(
        main_pc > 0x4000,
        "MAIN PC must have progressed deep into V3.1 app code (> 0x4000); got 0x{:04X}",
        main_pc
    );

    // CONTROL's shipped reset vector points at the Microchip
    // USB bootloader at 0x7800.  V1.71 ships the bootloader
    // image inline -- hex records starting at offset 0x7800
    // are real bootloader code (V1.71 hex line 1922:
    // `:107800007FEF3DF0...` = GOTO 0x7AFE → bootloader's
    // setup → user-code handoff).  After ~625 k Tcy CONTROL
    // has executed through the bootloader and back into
    // V1.71 user code (PC observed at 0x01E4 during
    // scaffolding).  Lock in "left the bootloader window"
    // with a strict `< 0x7800` upper bound (the K20's PC is
    // 21-bit but the program memory only spans
    // 0x0000..0x7FFF, so an out-of-bounds fetch would have
    // panicked via `ExecError::PcOutOfBounds` before reaching
    // this assertion -- the `>= 0x8000` allowance from the
    // prior commit was wrong and is dropped here).
    let control_pc = chain.cores[i_control].pc();
    assert!(
        control_pc < 0x7800,
        "CONTROL must be back in user code (PC < 0x7800), got 0x{:04X}",
        control_pc
    );

    // run_until exited because the predicate
    // `bytes_acked >= 1000` became true (or the 1 B safety
    // ceiling was hit -- we'd notice via current_tick and
    // a low ACK count).  The actual ACK count at exit will
    // overshoot 1000 by however many bytes the final
    // 10 M-tick chunk added on top.
    assert!(
        chain.tas3108_slaves[i_tas3108].bytes_acked >= 1000,
        "TAS3108 slave should have ACKed >= 1000 DSP-init bytes; got acked={}",
        chain.tas3108_slaves[i_tas3108].bytes_acked,
    );

    // Verify run_until actually exited early (not at the
    // safety ceiling).  Convergence at the prior fixed
    // 500 M budget showed ~6 k ACKs; the first 1 k must
    // land well before 1 B ticks.
    assert!(
        chain.current_tick < 1_000_000_000,
        "run_until hit the 1 B safety ceiling without converging; current_tick={}",
        chain.current_tick,
    );
}

/// V3.1 + V1.71 chain reaches its first UART TX byte across
/// the current loop.  This is the P3.5 *minimum-viable*
/// acceptance milestone: end-to-end demonstration that the
/// Rust simulator runs both shipped firmware images
/// concurrently through the chain dispatcher, with the
/// TAS3108 DSP responding on I2C and IRQ-driven CONTROL
/// state machine pumping its main loop.
///
/// **Full P3.5** per `docs/SIM_REWRITE_RUST_PROGRESS.md`
/// requires bit-exact TX byte streams + LCD raster
/// compared against gpsim ground truth.  Today's contract
/// is the strictly weaker "the chain converges on TX
/// traffic at all"; bit-exact comparison lands in P3.5
/// part-10+.
///
/// Convergence point during scaffolding (post-task-#28):
/// first UART TX at ~300 M universal ticks, ~2.7 s wall
/// locally.  600 M-tick safety ceiling gives ~2x headroom.
#[test]
fn chain_v171_v31_reaches_first_uart_tx() {
    let v171 = HexImage::from_hex_path(v171_control_hex_path())
        .expect("V1.71 hex parses");
    let v31 = HexImage::from_hex_path(v31_main_hex_path())
        .expect("V3.1 hex parses");

    let control = build_core_from_hex(Variant::Pic18F25K20, &v171, None);
    let mut main = build_core_from_hex(Variant::Pic18F2455, &v31, Some(0x1000));
    main.peripherals.adc.set_an0_sample(0x0300);

    let mut chain = Chain::new();
    let i_control = chain.push_core(control);
    let i_main = chain.push_core(main);
    chain.couple_uart(i_control, default_tx_pin(), i_main, default_rx_pin());
    chain.couple_uart(i_main, default_tx_pin(), i_control, default_rx_pin());
    let i_tas3108 = chain.push_tas3108(Tas3108::default());
    chain.couple_tas3108(i_main, i_tas3108);
    chain.apply_reset_all(ResetSource::PowerOn);
    chain.schedule_initial_steps(&[0, 0]);

    // Up to 600 M ticks (~13 s simulated, ~5 s wall locally
    // -- 2x the observed 2.7 s convergence budget gives
    // headroom for clock drift / scheduler overhead).  10 M-
    // tick chunks keep polling cadence at ~70 ms wall.
    let advanced = chain.run_until(
        10_000_000,
        600_000_000,
        |c| !c.uart_tx_history.is_empty(),
    );

    let tx_count = chain.uart_tx_history.len();
    let dsp_acked = chain.tas3108_slaves[i_tas3108].bytes_acked;
    let main_pc = chain.cores[i_main].pc();
    let control_pc = chain.cores[i_control].pc();

    // Hard-pass: at least one UART byte flowed within the
    // safety ceiling.  If this fires, EITHER the IRQ
    // dispatcher (task #28) regressed OR another peripheral
    // fidelity gap pushed the convergence point past
    // 600 M ticks.  Diagnostic state in the message helps
    // pinpoint which.
    assert!(
        tx_count >= 1,
        "V3.1 + V1.71 chain did NOT emit a UART byte within {} ticks: \
         tx_count={}, dsp_acked={}, main_pc=0x{:04X}, ctrl_pc=0x{:04X}.  \
         Either the IRQ dispatcher regressed (task #28) or another \
         peripheral fidelity gap pushed convergence past 600 M ticks.",
        advanced, tx_count, dsp_acked, main_pc, control_pc,
    );
}
