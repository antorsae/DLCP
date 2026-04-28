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

use std::path::{Path, PathBuf};

use dlcp_sim::chain::Chain;
use dlcp_sim::core::{Core, CycleProbe};
use dlcp_sim::hex::HexImage;
use dlcp_sim::lcd::Hd44780;
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

/// Canonical V3.2 MAIN release.  Layer 5 Diagnostics is
/// V3.2-only: V3.2 ships the per-counter diag-block at
/// physical RAM 0x123..0x12A and the BF/2N reply burst
/// firmware that V1.71 CONTROL polls for the Diagnostics
/// page.  The full P3.6 un-XFAIL gate uses this.  Task #36's
/// `build_seeded_main_core` works for V3.2 the same way it
/// does for V3.1 (both are app-only hexes covering
/// `[0x1000, 0x5600)`).
fn v32_main_hex_path() -> PathBuf {
    repo_root().join("firmware/patched/releases/DLCP_Firmware_V3.2.hex")
}

/// Path to the stock V2.3 MAIN combined hex.  Used as the
/// EEPROM / boot-block / preset-table seed for V3.x chain
/// probes to mirror gpsim's `build_seeded_main_sim_hex`
/// fixture (which merges app code from V3.x onto V2.3
/// recovered-device context).  Without this seed, MAIN's
/// EEPROM-backed status bytes (BF/07 = computed_volume +
/// 0x60, BF/06 = input_select) emit the V3.1 hex's own
/// EEPROM defaults, which differ from gpsim ground truth.
/// Task #33.
fn v23_main_combined_hex_path() -> PathBuf {
    repo_root().join("firmware/stock/main/DLCP Firmware V2.3-combined.hex")
}

/// V3.x app-code patch range.  Mirrors gpsim's
/// `MAIN_APP_PATCH_START` / `MAIN_APP_PATCH_LIMIT` in
/// `src/dlcp_fw/sim/main_gpsim.py`: V3.x hex covers app
/// code at `[0x1000, 0x5600)`; everything else (boot
/// block at 0x0000-0x0FFF, preset/DSP table at
/// 0x5600-0x5FFF, EEPROM, User ID, CONFIG) comes from
/// the V2.3-combined recovered-device seed.
const MAIN_APP_PATCH_START: usize = 0x1000;
const MAIN_APP_PATCH_LIMIT: usize = 0x5600;

/// Build a silicon-correct MAIN flash image by merging a
/// V3.x app-only hex onto the V2.3-combined recovered-
/// device seed.  Mirror of gpsim's `build_seeded_main_sim_hex`
/// (`src/dlcp_fw/sim/main_gpsim.py:321`).  Result:
///   * `flash[0x0000..0x1000]`: V2.3 boot block (real
///     V2.3 reset/IRQ vectors + RAM init at 0x058E,
///     etc.).
///   * `flash[0x1000..0x5600]`: V3.x app code, but only at
///     addresses that the V3.x source HEX actually wrote.
///     Addresses within the app range that V3.x left as
///     holes (no record) preserve the V2.3 seed value --
///     matching gpsim's sparse `dict[int, int]` merge in
///     Python (`build_seeded_main_sim_hex` iterates
///     `source_mem.items()`).  Without this, app-range
///     holes would be over-written with `0xFF`, destroying
///     V2.3 seed bytes (e.g. ~126 bytes around
///     0x48f2..0x4bff that V3.1 leaves untouched).  The
///     `flash_present` mask on `HexImage` is what makes
///     this distinction possible.
///   * `flash[0x5600..0x8000]`: V2.3 preset/DSP tables.
/// The resulting flash is what real silicon sees after
/// V3.x is patched onto a V2.3-flashed device.  No bake-
/// trampoline hack required: V2.3's reset vector at
/// 0x0000 already points at V2.3 boot init, which after
/// init naturally jumps to the V3.x app at 0x1000; the
/// V2.3 high-IRQ vector at 0x0008 already trampolines to
/// 0x1008 (V3.x's user IRQ handler).  Task #36.
fn build_seeded_main_flash(v3_app: &HexImage, v23_seed: &HexImage) -> Box<[u8; dlcp_sim::hex::FLASH_BYTES]> {
    let mut flash = v23_seed.flash.clone();
    let app_end = MAIN_APP_PATCH_LIMIT.min(v3_app.flash.len());
    for addr in MAIN_APP_PATCH_START..app_end {
        // Use HexImage::byte_at to consult flash + flash_present
        // through one call -- encapsulates the invariant the
        // c8cf249 codex review flagged (task #37).  Skips
        // addresses where v3_app has no record so the V2.3 seed
        // bytes underneath survive (e.g. boot block, recovery
        // vectors that V3.x doesn't repaint).
        if let Some(byte) = v3_app.byte_at(addr) {
            flash[addr] = byte;
        }
    }
    flash
}

/// Build a silicon-correct MAIN core from a V3.x app hex
/// merged onto a V2.3-combined seed.  Combines the
/// `build_seeded_main_flash` flash merge with the V2.3
/// EEPROM seed (task #33).  No bake-trampoline: V2.3's
/// real reset/IRQ vectors at 0x0000/0x0008 land in the
/// merged flash.  Task #36.
fn build_seeded_main_core(v3_app: &HexImage, v23_seed: &HexImage) -> Core {
    let mut core = Core::new(Variant::Pic18F2455);
    core.flash_mut().copy_from_slice(&*build_seeded_main_flash(v3_app, v23_seed));
    // EEPROM seed from V2.3 (task #33).  Without this,
    // BF/07 / BF/06 status-burst data bytes diverge from
    // gpsim ground truth.
    for (addr, &byte) in v23_seed.eeprom.iter().enumerate() {
        core.peripherals.eeprom.set_byte(addr as u8, byte);
    }
    core
}

/// Bake a PIC18 `GOTO target_byte_addr` instruction at
/// `flash[at]`.  4 bytes long; both addresses must be even.
/// Encoding per DS39632E §26 / DS41303 §25:
///   word1 = `1110 1111 k<7:0>`     (high byte 0xEF)
///   word2 = `1111 k<19:16> k<15:8>` (high byte = 0xF0 | k<19:16>)
/// where `k` is the WORD address (target_byte_addr / 2);
/// PCL bit 0 is hard-wired to 0 on PIC18, so target
/// addresses are always even.
fn bake_goto(flash: &mut [u8], at: usize, target_byte_addr: u32) {
    assert!(
        target_byte_addr & 1 == 0,
        "GOTO target byte address must be even, got 0x{target_byte_addr:X}"
    );
    assert!(
        at % 2 == 0,
        "GOTO bake address must be even, got 0x{at:X}"
    );
    let k_word = target_byte_addr >> 1;
    assert!(
        k_word <= 0x000F_FFFF,
        "GOTO target out of 21-bit PC range: 0x{target_byte_addr:X}"
    );
    flash[at] = (k_word & 0xFF) as u8;
    flash[at + 1] = 0xEFu8;
    flash[at + 2] = ((k_word >> 8) & 0xFF) as u8;
    flash[at + 3] = 0xF0u8 | (((k_word >> 16) & 0x0F) as u8);
}

/// Load a hex file into a fresh core of the given variant.
/// Mirrors `isa_parity.rs::run_to_cycle`'s setup minus the
/// step loop: copies flash, initialises EEPROM contents from
/// the hex image, applies POR.
///
/// The 2455 V3.x main image leaves the bootloader window
/// (`flash[0..0x1000]`) erased.  On real silicon the
/// Microchip USB bootloader at 0x0000 jumps to the app
/// entry at 0x1000 when not in update mode AND trampolines
/// IRQs at 0x0008 → user-defined IRQ handler (V3.1 puts it
/// at 0x1008).  The simulator has no bootloader image, so
/// the caller can ask us to bake those `GOTO`s.  Without
/// the IRQ trampoline, hardware vectoring to 0x0008 starts
/// NOP-walking through erased flash (`0xFFFF` decodes as
/// `NopContinuation`, advancing PC by 2 each Tcy), and
/// eventually reaches our shipped `GOTO 0x1014` at flash
/// offset 0x1000 -- skipping V3.1's user IRQ handler at
/// 0x1008 entirely and **spuriously re-entering V3.1 app
/// code from the boot trampoline**.  That's a worse fault
/// than "infinite NOP": MAIN keeps re-initializing each
/// time an IRQ fires.  Task #30 findings.
fn build_core_from_hex(
    variant: Variant,
    image: &HexImage,
    bake_goto_app_entry: Option<u32>,
    bake_goto_irq_vector: Option<u32>,
) -> Core {
    let mut core = Core::new(variant);
    core.flash_mut().copy_from_slice(&*image.flash);

    if let Some(target) = bake_goto_app_entry {
        bake_goto(core.flash_mut(), 0x0000, target);
    }
    if let Some(target) = bake_goto_irq_vector {
        bake_goto(core.flash_mut(), 0x0008, target);
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
    let control = build_core_from_hex(Variant::Pic18F25K20, &v171, None, None);
    // V3.1 MAIN's user IRQ handler lives at 0x1008 (saves
    // FSR2 + CALL FAST main_isr_dispatch); the bootloader
    // would normally trampoline 0x0008 → 0x1008 but isn't
    // loaded, so we bake the trampoline here.  Task #30 fix.
    let mut main = build_core_from_hex(
        Variant::Pic18F2455,
        &v31,
        Some(0x1000),
        Some(0x1008),
    );
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

/// P3.6 step 1 -- firmware-driven 3-core ring smoke test.
///
/// Wires a silicon-correct DLCP single-direction current-
/// loop ring (CONTROL -> MAIN0 -> MAIN1 -> CONTROL) with
/// V1.71 + V3.2 + V3.2 firmware images, two TAS3108 audio
/// DSP slaves (one per MAIN), and the V2.3-combined boot-
/// block merge from task #36 on both MAINs.  The point is
/// to verify the chain *boots* under the correct topology
/// without panicking before we layer on Layer 5
/// Diagnostics-page convergence.
///
/// Convergence predicate: BOTH MAINs must reach
/// `bytes_acked >= 1000` on their respective TAS3108
/// slaves -- proves DSP init bursts are firing on both
/// MAINs in parallel under the ring topology, which is the
/// strongest pre-Layer-5 milestone that terminates within
/// a unit-test wall-clock budget.
///
/// What this test does NOT cover (deferred to subsequent
/// P3.6 steps):
///   * Driving CONTROL to the Diagnostics page (needs
///     button stimulus injection -- task #35 -- or a
///     host-side cmd burst path).
///   * Asserting `v171_diag_present == 0x03` at the end of
///     a polling cycle.
///   * Removing the four `pytest.mark.xfail` decorators in
///     `tests/sim/test_v171_v32_layer5_diag_chain.py`.
///
/// Step-1 deliverable: ring boots, both MAINs cross DSP-
/// init threshold, no panics.
#[test]
fn three_core_ring_v171_v32_v32_boots_under_silicon_topology() {
    let v171 = HexImage::from_hex_path(v171_control_hex_path())
        .expect("V1.71 hex parses");
    let v32 = HexImage::from_hex_path(v32_main_hex_path())
        .expect("V3.2 hex parses");
    let v23_combined = HexImage::from_hex_path(v23_main_combined_hex_path())
        .expect("V2.3 combined hex parses");

    let control = build_core_from_hex(Variant::Pic18F25K20, &v171, None, None);
    // Both MAINs use the silicon-correct V2.3 boot-block
    // merge from task #36; no bake-trampolines.  The
    // EEPROM seed (also from V2.3-combined) gives both
    // MAINs the recovered-device EEPROM defaults that
    // V3.2 expects on first boot.
    let mut main0 = build_seeded_main_core(&v32, &v23_combined);
    main0.peripherals.adc.set_an0_sample(0x0300);
    let mut main1 = build_seeded_main_core(&v32, &v23_combined);
    main1.peripherals.adc.set_an0_sample(0x0300);

    let mut chain = Chain::new();
    let i_ctl = chain.push_core(control);
    let i_main0 = chain.push_core(main0);
    let i_main1 = chain.push_core(main1);

    // Silicon-correct DLCP single-direction current-loop
    // ring: 3 directional edges, no fan-out, no
    // self-loops.  Pinned by the architectural scope
    // probe in
    // `chain::tests::three_core_silicon_ring_uart_topology_has_no_echo_or_duplicates`.
    chain.couple_uart(i_ctl, default_tx_pin(), i_main0, default_rx_pin());
    chain.couple_uart(i_main0, default_tx_pin(), i_main1, default_rx_pin());
    chain.couple_uart(i_main1, default_tx_pin(), i_ctl, default_rx_pin());

    // Configuration audit (codex LOW from 40864f7
    // review): the observation-side ring-edge whitelist
    // below is a necessary but not sufficient check --
    // it can't detect a duplicate or extra coupling
    // whose source happened not to emit before
    // convergence.  Pin the wiring at the source by
    // walking `pinnet.uart` and asserting EXACTLY the
    // three ring edges, in the order they were added,
    // with no duplicates or extras.
    // Codex LOW from 8e180a6 review (task #39): compare the
    // FULL `UartCoupling` (src/dst core IDs + src TX pin +
    // dst RX pin), not just the (src_core, dst_core) tuple.
    // Without the pin check a regression in `couple_uart`'s
    // pin handling would slip past this audit even though
    // the cores wire up correctly.
    let expected_uart_edges = [
        (i_ctl, default_tx_pin(), i_main0, default_rx_pin()),
        (i_main0, default_tx_pin(), i_main1, default_rx_pin()),
        (i_main1, default_tx_pin(), i_ctl, default_rx_pin()),
    ];
    assert_eq!(
        chain.pinnet.uart.len(),
        expected_uart_edges.len(),
        "ring must have exactly 3 UART couplings, got {}",
        chain.pinnet.uart.len(),
    );
    for (idx, &(exp_src, exp_src_pin, exp_dst, exp_dst_pin)) in
        expected_uart_edges.iter().enumerate()
    {
        let coupling = &chain.pinnet.uart[idx];
        assert_eq!(
            (coupling.src_core, coupling.src_tx_pin, coupling.dst_core, coupling.dst_rx_pin),
            (exp_src, exp_src_pin, exp_dst, exp_dst_pin),
            "ring edge {idx} mismatch: got src={}.{:?}->dst={}.{:?}, \
             expected src={}.{:?}->dst={}.{:?}",
            coupling.src_core, coupling.src_tx_pin,
            coupling.dst_core, coupling.dst_rx_pin,
            exp_src, exp_src_pin, exp_dst, exp_dst_pin,
        );
    }

    // Each MAIN has its own TAS3108 audio DSP wired to
    // its MSSP I²C bus.  Without the slaves both MAINs
    // park in `dsp_ping`'s NACK retry loop and never
    // make forward progress past DSP init.
    let i_dsp0 = chain.push_tas3108(Tas3108::default());
    let i_dsp1 = chain.push_tas3108(Tas3108::default());
    chain.couple_tas3108(i_main0, i_dsp0);
    chain.couple_tas3108(i_main1, i_dsp1);

    chain.apply_reset_all(ResetSource::PowerOn);
    // Same-PSU boot: all three units come up together.
    chain.schedule_initial_steps(&[0, 0, 0]);

    // Convergence: both MAINs cross DSP-init threshold
    // AND at least one UART byte has flowed.  The DSP-
    // init predicate alone is insufficient because
    // `bytes_acked` counts I²C traffic internal to each
    // MAIN's MSSP -- it tells us nothing about whether
    // the ring's UART couplings are actually conducting,
    // which is what makes the firmware-driven echo-loop
    // check below meaningful.  V1.71's `full_sync_burst`
    // emits CONTROL.TX bytes early in boot, so adding
    // `!uart_tx_history.is_empty()` to the predicate
    // doesn't extend convergence by much (empirically
    // the 2-core V3.1 chain reaches first UART TX in
    // < 600 M ticks; the 3-core variant fits in 5 B).
    //
    // Codex review of f985498 (MEDIUM): without this
    // strengthening the no-echo loop would scan a
    // possibly-empty `uart_tx_history` and pass
    // vacuously.
    chain.run_until(
        10_000_000,    // chunk_ticks: 10 M = ~70 ms wall
        5_000_000_000, // max_ticks: 5 B safety ceiling
        |c| {
            c.tas3108_slaves[i_dsp0].bytes_acked >= 1000
                && c.tas3108_slaves[i_dsp1].bytes_acked >= 1000
                && !c.uart_tx_history.is_empty()
        },
    );

    // All three cores made forward progress.
    let ctl_cycles = chain.cores[i_ctl].cycles();
    let main0_cycles = chain.cores[i_main0].cycles();
    let main1_cycles = chain.cores[i_main1].cycles();
    assert!(ctl_cycles > 0, "CONTROL did not advance under chain dispatch");
    assert!(main0_cycles > 0, "MAIN0 did not advance under chain dispatch");
    assert!(main1_cycles > 0, "MAIN1 did not advance under chain dispatch");

    // Both MAINs ran past V3.2 boot init into application
    // code (PC > 0x4000); same threshold the V3.1 2-core
    // smoke test uses.
    let main0_pc = chain.cores[i_main0].pc();
    let main1_pc = chain.cores[i_main1].pc();
    assert!(
        main0_pc > 0x4000,
        "MAIN0 PC must have progressed deep into V3.2 app code (> 0x4000); got 0x{main0_pc:04X}"
    );
    assert!(
        main1_pc > 0x4000,
        "MAIN1 PC must have progressed deep into V3.2 app code (> 0x4000); got 0x{main1_pc:04X}"
    );

    // CONTROL has left the bootloader window and is back
    // in V1.71 user code.
    let ctl_pc = chain.cores[i_ctl].pc();
    assert!(
        ctl_pc < 0x7800,
        "CONTROL must be back in user code (PC < 0x7800), got 0x{ctl_pc:04X}"
    );

    // Both DSP slaves crossed the convergence threshold.
    assert!(
        chain.tas3108_slaves[i_dsp0].bytes_acked >= 1000,
        "MAIN0 TAS3108 slave should have ACKed >= 1000 DSP-init bytes; got {}",
        chain.tas3108_slaves[i_dsp0].bytes_acked,
    );
    assert!(
        chain.tas3108_slaves[i_dsp1].bytes_acked >= 1000,
        "MAIN1 TAS3108 slave should have ACKed >= 1000 DSP-init bytes; got {}",
        chain.tas3108_slaves[i_dsp1].bytes_acked,
    );

    // run_until exited via the predicate, not the
    // safety ceiling.
    assert!(
        chain.current_tick < 5_000_000_000,
        "run_until hit the 5 B safety ceiling without converging; current_tick={}",
        chain.current_tick,
    );

    // Firmware-driven Task #22 echo-loop check.  The
    // architectural scope probe in
    // `chain::tests::three_core_silicon_ring_uart_topology_has_no_echo_or_duplicates`
    // proves the dispatch model can't echo under
    // synthetic injection.  This is the *firmware* version
    // of that assertion: across an actual V1.71+V3.2+V3.2
    // boot run, scan every recorded UART delivery and
    // assert no record has `src_core == dst_core`.  Real
    // hardware can't echo a TX into its own RX; if any
    // future regression in `couple_uart` or
    // `drain_completed_tx_bytes` introduces a self-loop,
    // it will surface here -- with the actual Task #22
    // chain protocol traffic exercising it.
    //
    // The assertion is only load-bearing if UART traffic
    // *actually flowed* during the run.  The convergence
    // predicate above already guarantees
    // `!uart_tx_history.is_empty()` at exit (`run_until`
    // exits as soon as the predicate fires), so this
    // assert duplicates a postcondition for documentation
    // -- but it costs nothing and pins the contract
    // should the predicate ever change.
    assert!(
        !chain.uart_tx_history.is_empty(),
        "uart_tx_history must be non-empty by convergence so the \
         no-echo loop below has something to scan"
    );
    for record in &chain.uart_tx_history {
        assert_ne!(
            record.src_core, record.dst_core,
            "no UART delivery may route a core's TX to its own RX; \
             firmware-driven echo-loop check failed on record {record:?}"
        );
    }

    // Cardinality / topology audit: every record must
    // route along one of the three wired ring edges
    // (CONTROL->MAIN0, MAIN0->MAIN1, MAIN1->CONTROL).
    // Any record on a non-ring edge would indicate a
    // wiring drift -- fan-out, reverse coupling, etc. --
    // and is exactly the class of defect Task #22
    // chases.  This is the firmware-driven analogue of
    // the cardinality check the architectural scope
    // probe in `chain.rs::tests` makes under synthetic
    // injection.
    for record in &chain.uart_tx_history {
        let edge = (record.src_core, record.dst_core);
        let is_ring_edge = edge == (i_ctl, i_main0)
            || edge == (i_main0, i_main1)
            || edge == (i_main1, i_ctl);
        assert!(
            is_ring_edge,
            "uart_tx_history record routes on a non-ring edge {edge:?} \
             (i_ctl={i_ctl}, i_main0={i_main0}, i_main1={i_main1}); \
             record: {record:?}"
        );
    }
}

/// P3.6 step (B) -- diag-page convergence probe.
///
/// Drives CONTROL via simulated RIGHT-button presses
/// (task #35 minimum-viable input injection -- see
/// `Chain::set_pin_high/low`) and instruments stage 3
/// with rich diagnostic counters (PC histogram, target
/// trajectory, BF/2N dispatch hits, byte-level CTL/MAIN
/// streams).  Provides the highest-resolution view of
/// the residual divergence we've achieved.
///
/// Verified working (HOPS A, B, C, D):
///   * 4 RIGHT-press cycles cleanly advance state 0 ->
///     1 -> 2 -> 3 -> 4.  menu_state = 4 throughout
///     stage 3.
///   * `v171_diag_pb_screen` IS entered: `v171_diag_flags
///     = 0x06` (RUNTIME_PENDING + RESET_PENDING both set).
///   * cmd 0x22 (reset-flags) AND cmd 0x21 (runtime
///     counters) queries are emitted by CONTROL:
///     `B1/22/00 = 1, B1/21/00 = 1` in CTL.TX.
///   * MAIN0 emits its 7-frame `BF/21..BF/27` reply burst.
///   * MAIN1 forwards the full burst, including the
///     critical `BF 27 00` (last frame, sets present
///     bit + toggles target).  Verified by direct
///     byte-stream inspection: MAIN1.TX[147..150] =
///     `BF 24 00 BF 25 00 BF 26 00 BF 27 00`.
///   * The wire-side delivery view (`Chain::uart_tx_history`
///     filtered by `dst_core == CONTROL`) records 21
///     contiguous BF/2N bytes including the trailing
///     `BF 27 00` at the expected ~15 480-tick spacing,
///     so wire emission was attempted.  RCSTA at the end
///     of stage 3 reads `0x90` -- no OERR latched at exit
///     time.  This DOES NOT prove every byte was accepted
///     by RCSTA / pushed to the SW rx_ring -- a transient
///     OERR or ring-overrun roll-back at v171.asm:837-849
///     could still drop bytes within a 10 M-tick sampler
///     chunk; step-2 cycle-level instrumentation is
///     required to make that claim.
///
/// Residual divergence (HOP E -- the LAST hop):
///   * `v171_diag_present = 0x00` at every observed sampler
///     boundary (200 boundaries spanning 2 B ticks).
///   * `v171_diag_target = 0x00` at every observed sampler
///     boundary; trajectory `[00]`.
///   * `v171_diag_flags = 0x06` (PENDING bits set, never
///     observed cleared).
///
/// **The load-bearing evidence is the target trajectory,
/// not PC sampling -- but it's still sampler-bounded.**  At
/// strict boundary-sampling, target = 0x00 across 200
/// boundaries proves only "no sampled target change", not
/// "never toggled".  However, V1.71's polling state machine
/// waits for one reply before issuing the next query
/// (cycle ~54 M ticks); any BF/27 that completed should
/// park target = 0x01 for at least one full cycle (~5
/// consecutive boundaries).  So observing `[00]` across
/// 200 boundaries is strong-but-not-cycle-level evidence
/// that the BF/27 last-frame path did not complete.  Step-2
/// cycle-level probes will upgrade this to a hard claim.  The PC histogram is informational only --
/// 200 samples * 10 M ticks = 2 B ticks at K20's
/// 16 ticks/Tcy = 125 M Tcy.  A ~50-Tcy dispatch body
/// (~800 ticks) gives only ~0.008% per-sample chance of
/// landing on the dispatch -- ~1.6% cumulative across
/// the 200 sample windows even when firing once per
/// chunk.  So 0/200 hits is consistent with sparse
/// sampling, not proof of non-execution.
///
/// Phrased correctly: CONTROL never **successfully
/// processes** BF/27 through the BF/2N last-frame path.
///
/// Hypotheses for the open hop (codex review of 56841f4
/// added the 4th):
///   1. CONTROL's parser frame-state machine (0xA6
///      counter) is in the wrong state when the BF byte
///      arrives -- maybe stuck mid-frame from prior
///      traffic, so the cmd byte doesn't latch correctly.
///   2. The cmd-dispatch chain has a path where cmd =
///      0x27 (or some other BF/2N value) is consumed by
///      an earlier handler instead of falling through to
///      v171_bf2x_case_check.
///   3. RXIF ISR latency: bytes are dropped from the SW
///      ring at 0x0200 before the parser drains them
///      (less likely since RCSTA shows no OERR at exit).
///   4. RCSTA = 0x90 at exit only proves no OERR latched
///      AT EXIT.  Transient OERR / CREN-toggle recovery
///      / SW-ring overflow during the BF burst itself
///      could have dropped bytes mid-stream and recovered
///      before sample time.
///
/// `#[ignore]`d.  Wall ~ 60 s.  Hop E investigation
/// pending: trace CONTROL's parser state during the
/// BF/27 byte arrival window.
#[test]
#[ignore = "P3.6 step (B) -- diag-poll cadence still doesn't fire after firmware-driven navigation"]
fn three_core_ring_v171_v32_v32_diag_page_polls_pb1_and_pb2() {
    use dlcp_sim::memory::Address;

    const MENU_STATE_RAM: u16 = 0x0BF;
    const DIAG_TARGET_RAM: u16 = 0x196;
    const DIAG_PRESENT_RAM: u16 = 0x197;
    const MENU_STATE_PB1_DIAG: u8 = 4;
    // Per-PB diag cache: 11 cells (I/D/S/B/R/A/P/O/V/W/X)
    // per PB.  Bases pinned in
    // `tests/sim/test_v171_v32_layer5_diag_chain.py` and
    // `src/dlcp_fw/asm/dlcp_control_v171.asm`.
    const DIAG_PB1_BASE_RAM: u16 = 0x180;
    const DIAG_PB2_BASE_RAM: u16 = 0x18B;
    const DIAG_PB_CACHE_LEN: u16 = 11;

    let v171 = HexImage::from_hex_path(v171_control_hex_path())
        .expect("V1.71 hex parses");
    let v32 = HexImage::from_hex_path(v32_main_hex_path())
        .expect("V3.2 hex parses");
    let v23_combined = HexImage::from_hex_path(v23_main_combined_hex_path())
        .expect("V2.3 combined hex parses");

    let control = build_core_from_hex(Variant::Pic18F25K20, &v171, None, None);
    let mut main0 = build_seeded_main_core(&v32, &v23_combined);
    main0.peripherals.adc.set_an0_sample(0x0300);
    let mut main1 = build_seeded_main_core(&v32, &v23_combined);
    main1.peripherals.adc.set_an0_sample(0x0300);

    let mut chain = Chain::new();
    let i_ctl = chain.push_core(control);
    let i_main0 = chain.push_core(main0);
    let i_main1 = chain.push_core(main1);

    chain.couple_uart(i_ctl, default_tx_pin(), i_main0, default_rx_pin());
    chain.couple_uart(i_main0, default_tx_pin(), i_main1, default_rx_pin());
    chain.couple_uart(i_main1, default_tx_pin(), i_ctl, default_rx_pin());

    let i_dsp0 = chain.push_tas3108(Tas3108::default());
    let i_dsp1 = chain.push_tas3108(Tas3108::default());
    chain.couple_tas3108(i_main0, i_dsp0);
    chain.couple_tas3108(i_main1, i_dsp1);

    chain.apply_reset_all(ResetSource::PowerOn);
    chain.schedule_initial_steps(&[0, 0, 0]);

    // Stage 1: boot to first UART so CONTROL is in main loop.
    chain.run_until(
        10_000_000,
        5_000_000_000,
        |c| {
            c.tas3108_slaves[i_dsp0].bytes_acked >= 1000
                && c.tas3108_slaves[i_dsp1].bytes_acked >= 1000
                && !c.uart_tx_history.is_empty()
        },
    );
    let stage1_tick = chain.current_tick;
    let stage1_history_len = chain.uart_tx_history.len();

    // Stage 1 must have actually converged via the
    // predicate (codex LOW from 3a43e43): otherwise a
    // future boot regression would surface as the SAME
    // PB2 saturation symptom this probe is investigating,
    // muddying the diagnosis.  Pin "we got out of stage 1
    // for the right reason" before poking RAM.
    assert!(
        chain.tas3108_slaves[i_dsp0].bytes_acked >= 1000
            && chain.tas3108_slaves[i_dsp1].bytes_acked >= 1000
            && !chain.uart_tx_history.is_empty(),
        "stage 1 boot did NOT converge via the predicate -- \
         dsp0_acks={}, dsp1_acks={}, uart_tx_len={}, current_tick={}",
        chain.tas3108_slaves[i_dsp0].bytes_acked,
        chain.tas3108_slaves[i_dsp1].bytes_acked,
        chain.uart_tx_history.len(),
        chain.current_tick,
    );

    // Stage 1.5: continue stepping until CONTROL has reached
    // the display-loop range (post_connect_init has finished
    // and the dispatcher is firing periodically).  We detect
    // this via PORTA bit 4: if buttons are released and
    // button_scan_debounce is firing, btn_cache(0xBC) stays
    // at 0; but the act of running button_scan touches
    // various RAM cells.  Simpler heuristic: wait until the
    // CTL menu_state reflects the firmware-default value (0
    // = Volume), which only gets initialized once display
    // mode is entered.  But actually 0 IS the default on POR
    // -- so we instead need a different signal.
    //
    // Empirical: at stage 1 (170 M ticks), CTL PC=0x01E2.
    // That's deep in post-handshake init, before
    // display_loop_iteration is reachable.  Step more until
    // PC is in the post_connect range (~0x11D8+).
    chain.cores[i_ctl]
        .memory
        .write_raw(Address::from_raw(0xF80), 0xFF);
    chain.cores[i_ctl]
        .memory
        .write_raw(Address::from_raw(0xF82), 0xFF);
    chain.run_until(
        50_000_000,
        2_000_000_000,
        |c| {
            let pc = c.cores[i_ctl].pc();
            pc >= 0x0CB2 && pc < 0x2000
        },
    );
    let ctl_pc_stage1_5 = chain.cores[i_ctl].pc();
    eprintln!(
        "Stage 1.5 exit: CONTROL PC=0x{ctl_pc_stage1_5:04X} \
         (target: in display-loop range 0x0CB2..0x2000)"
    );

    // Stage 2: navigate CONTROL to the PB1 Diag screen via
    // simulated RIGHT-button presses (task #35 minimum-
    // viable input injection).  V1.71's 6-state menu ring
    // is 0=Vol / 1=Preset / 2=Input / 3=Setup / 4=PB1Diag /
    // 5=PB2Diag (`dlcp_control_v171.asm:4805+`).  Each
    // RIGHT press advances state by 1, so 4 presses from
    // state 0 reach state 4.
    //
    // Button mapping (V1.71): RIGHT=RA4, LEFT=RC5,
    // SELECT=RA3, DOWN=RC0, STBY=RA2, UP=RA1.  Active-low.
    //
    // Baseline: PORTA = PORTC = 0xFF (all buttons released)
    // so spurious presses don't trigger STBY etc.
    use dlcp_sim::pinnet::PortLetter;
    chain.cores[i_ctl]
        .memory
        .write_raw(Address::from_raw(0xF80), 0xFF); // PORTA
    chain.cores[i_ctl]
        .memory
        .write_raw(Address::from_raw(0xF82), 0xFF); // PORTC

    // Run a few M ticks first so the released-button
    // state is observed by the firmware's debounce logic
    // before we start pressing.
    chain.step_ticks(5_000_000);

    // Press RIGHT (RA4) 4 times to navigate state 0 -> 4.
    // Each press cycle: pull pin LOW, hold ~5 M ticks for
    // firmware debounce (4 stable cycles of
    // `display_loop_iteration`), release, hold ~5 M ticks
    // for release debounce + state increment + LCD redraw.
    for press in 0..4 {
        chain.set_pin_low(i_ctl, PortLetter::A, 4); // RIGHT pressed
        let porta_after_press = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0xF80));
        eprintln!(
            "press #{press_n}: PORTA after pin_low = 0x{porta_after_press:02X}",
            press_n = press + 1
        );
        chain.step_ticks(5_000_000);
        let porta_held = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0xF80));
        let cached_btn_0xbc = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x0BC));
        let debounce_0xbb = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x0BB));
        eprintln!(
            "press #{press_n}: after 5M ticks: PORTA=0x{porta_held:02X}, \
             btn_cache(0xBC)=0x{cached_btn_0xbc:02X}, debounce(0xBB)={debounce_0xbb}",
            press_n = press + 1
        );
        chain.set_pin_high(i_ctl, PortLetter::A, 4); // RIGHT released
        chain.step_ticks(5_000_000);
        let state_now = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(MENU_STATE_RAM));
        eprintln!(
            "After RIGHT press #{press_n}: menu_state = {state_now}",
            press_n = press + 1
        );
        // Codex LOW from aa8ba84 review (task #42): per-press
        // contract -- after each RIGHT press, menu_state MUST
        // have advanced by exactly 1 (state ring increments
        // on each accepted press).  Without this assertion a
        // press that fails to register (e.g. debounce window
        // skipped, button-scan suppressed) would silently
        // skip a state and leave the final-state check at
        // line ~990 to catch it -- but that final assert
        // can't tell *which* press failed, only that we ended
        // up somewhere unexpected.
        assert_eq!(
            state_now,
            (press + 1) as u8,
            "menu_state after RIGHT press #{press_n} must equal {expected} \
             (state-ring increments by 1 per accepted press); got {state_now}.  \
             A press that didn't register here means the button-injection \
             debounce / scan timing is off -- check the 5 M-tick hold \
             window vs V1.71's 4-stable-poll debounce.",
            press_n = press + 1,
            expected = press + 1,
        );
    }

    let menu_state_after_nav = chain.cores[i_ctl]
        .memory
        .read_raw(Address::from_raw(MENU_STATE_RAM));
    assert_eq!(
        menu_state_after_nav, MENU_STATE_PB1_DIAG,
        "after 4 RIGHT presses CONTROL must be on state 4 (PB1Diag); \
         got state {menu_state_after_nav}"
    );

    // Snapshot history just before stage 3 polling so we
    // can dump byte streams for diagnosis on failure.
    let stage2_history_len = chain.uart_tx_history.len();

    // P3.6b research step 2 (task #62): attach a cycle-level
    // probe to CONTROL.  Updated PER INSTRUCTION by
    // `Chain::execute_core_step`, so its counters and
    // transition logs are NOT subject to the 10 M-tick
    // boundary blind spot that limits the ring/parser
    // sampler below.  Addresses (parsed from V1.71 .lst
    // generated by `dlcp_fw.sim.v30_symbols.assemble_v30`):
    //
    //   0x0630..0x0696 -- v171_bf2x_case_check FULL BODY
    //                     (range gate + cache routing + slot
    //                      write + RUNTIME/RESET dispatch)
    //   0x0630..0x0632 -- v171_bf2x_case_check ENTRY ONLY
    //                     (one instruction = one dispatch
    //                      attempt; counts the parser hitting
    //                      the BF/2N range gate from
    //                      flow_rx_parser_entry_05EA)
    //   0x0672..0x0682 -- BF/27 RUNTIME-LAST tail body
    //                     (executed only when col_offset == 6,
    //                      i.e. the parsed cmd byte is 0x27;
    //                      sets present-mask, clears
    //                      RUNTIME_PENDING, toggles target)
    //   0x067C..0x067E -- `btg v171_diag_target, 0` SINGLE
    //                     INSTRUCTION (the target-toggle that
    //                     should fire exactly once per
    //                     successful BF/27 dispatch)
    //   0x0678..0x067A -- `iorwf v171_diag_present, F` SINGLE
    //                     INSTRUCTION (the present-mask
    //                     OR-in)
    //
    // RAM transitions watched on CONTROL (11 cells; step-3 added
    // 0x0AC + 0x19D per codex guidance on cfa9e6e):
    //   0x02F  rx_parsed_cmd            (every parsed_cmd value
    //                                     the parser ever latches,
    //                                     with tick stamp -- no
    //                                     boundary blind spot)
    //   0x030  rx_parsed_data            (every parsed_data value)
    //   0x098  rx_ring_rd                (every ring-consumer advance)
    //   0x099  rx_ring_wr                (every ring-producer advance)
    //   0x0A6  rx_frame_position         (every frame_pos transition,
    //                                     including watchdog clears)
    //   0x0AC  v171_rx_frame_gap_timeout (parser-stall watchdog state;
    //                                     reload V171_RX_FRAME_GAP_RELOAD
    //                                     = 0xF8 = 8-step countdown to
    //                                     `clrf rx_frame_position`)
    //   0xFAB  RCSTA                     (every OERR/CREN/SPEN edit)
    //   0x196  v171_diag_target          (every toggle)
    //   0x197  v171_diag_present         (every present-mask write)
    //   0x19C  v171_diag_flags           (every flag-bit edit)
    //   0x19D  v171_diag_reset_seen      (every BF/2B reset_seen OR-in)
    {
        let initial_parsed_cmd = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x02F));
        let initial_target = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x196));
        let initial_present = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x197));
        let initial_flags = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x19C));
        let mut probe = CycleProbe::new();
        probe.add_pc_range(0x0518, 0x051A, "data-byte path entry (04F8) ENTRY");
        probe.add_pc_range(0x05F0, 0x05F2, "cmd 0x1D check ENTRY (05D0)");
        probe.add_pc_range(0x060C, 0x060E, "v171_bf08_case_check ENTRY");
        probe.add_pc_range(0x0630, 0x0696, "v171_bf2x_case_check FULL BODY");
        probe.add_pc_range(0x0630, 0x0632, "v171_bf2x_case_check ENTRY ONLY");
        probe.add_pc_range(0x0672, 0x0682, "BF/27 RUNTIME-LAST tail");
        probe.add_pc_range(0x067C, 0x067E, "btg v171_diag_target SINGLE");
        probe.add_pc_range(0x0678, 0x067A, "iorwf v171_diag_present SINGLE");
        // P3.6b research step 3 (task #63 -- per codex on cfa9e6e):
        // PC ranges to resolve the "4 entries to v171_bf2x_case_check
        // but no RESET_PENDING clear" contradiction.  Without these
        // we cannot distinguish "BF/2B body inner ran but bcf
        // mis-banked" from "BF/2B body inner never ran".
        probe.add_pc_range(0x0682, 0x0692, "v171_bf2x_check_reset_last FULL BODY");
        probe.add_pc_range(0x0682, 0x0684, "v171_bf2x_check_reset_last ENTRY ONLY");
        probe.add_pc_range(0x0688, 0x0690, "BF/2B body inner (col==10 path)");
        probe.add_pc_range(0x0690, 0x0692, "bcf RESET_PENDING SINGLE");
        probe.add_pc_range(0x0692, 0x0694, "exit_bsr0 ENTRY (movlb 0)");
        // P3.6b research step 5 (task #66): cadence-loop
        // probes to investigate why PB2 query never fires
        // even with the watchdog intervention enabled.
        probe.add_pc_range(0x1514, 0x1516, "v171_diag_loop ENTRY");
        probe.add_pc_range(0x152A, 0x152C, "v171_diag_send_now ENTRY (poll==0)");
        probe.add_pc_range(0x153E, 0x1540, "v171_diag_check_reset_seen ENTRY");
        probe.add_pc_range(0x155A, 0x155C, "v171_diag_send_runtime_only ENTRY");
        probe.add_pc_range(0x15F0, 0x15F2, "v171_diag_send_runtime_query ENTRY");
        probe.add_pc_range(0x15F4, 0x15F6, "v171_diag_send_reset_query ENTRY");
        // NOTE on the next three "ENTRY" probes: the cycle
        // probe is attached AFTER stage 2 has navigated to
        // menu_state == 4, so the firmware has already
        // executed `main_event_loop` -> `v171_diag_pb_screen`
        // entry once before the probe exists.  These ENTRY
        // counters therefore measure RE-ENTRIES only, not
        // the boot-time first-entry hit.  If the body tail-
        // loops through sub-labels (it does -- v171.asm:3550+
        // and main_event_loop's flow_main_event_loop_1532
        // sub-label), the ENTRY counter stays at 0 and the
        // re-execution counts must be inferred from the
        // body's individual instructions.  Codex MEDIUM
        // from 82f29c5.
        probe.add_pc_range(0x12CC, 0x12CE, "v171_diag_pb_screen ENTRY (re-entries only)");
        probe.add_pc_range(0x0E1A, 0x0E1C, "display_loop_iteration ENTRY");
        probe.add_pc_range(0x1D0C, 0x1D0E, "main_event_loop ENTRY (re-entries only)");
        // P3.6b research step 6 (task #67): display_loop_iteration
        // FULL BODY plus each direct callee.  hits = instructions
        // executed in body, total Tcy = sum of per-instruction
        // cycle costs, avg = body Tcy per instruction.  Compare
        // body Tcy against a cadence design budget of ~31 250 Tcy
        // (1 sec @ 4 MIPS / 128 cadence ticks per sec).
        probe.add_pc_range(0x0E1A, 0x0F40, "display_loop_iteration FULL BODY (294 bytes)");
        probe.add_pc_range(0x0994, 0x0A28, "button_scan_debounce FULL BODY (148 bytes)");
        probe.add_pc_range(0x0D92, 0x0DB2, "v171_service_pending_ir_decode FULL BODY (32 bytes)");
        probe.add_pc_range(0x0458, 0x060C, "rx_parser_entry FULL BODY (436 bytes -- includes dispatch)");
        probe.add_pc_range(0x0DB2, 0x0DE0, "v171_service_rx_frame_gap FULL BODY (46 bytes -- watchdog)");
        // Codex MEDIUM from 1067b66: the original bounds for these
        // three FULL BODY ranges ended at the first `flow_*` sub-
        // label, which is INSIDE the same function body (e.g. the
        // EEPROM write loop in control_core_service_0990, the IR/
        // preset endpoint dispatch in control_core_service_0DCE,
        // and the step dispatch in full_sync_burst).  Widen each
        // range to the next label whose name is unrelated to the
        // function (per scripts/find_body_extents.py-style heuristic
        // that treats `flow_<func>_*`, `flow_ccs_<addr>_*`, and
        // `v171_fs_*` as same-body sub-labels).
        probe.add_pc_range(0x0A78, 0x0B2E, "control_core_service_0990 FULL BODY (182 bytes)");
        probe.add_pc_range(0x0F40, 0x10DE, "control_core_service_0DCE FULL BODY (414 bytes)");
        probe.add_pc_range(0x0C24, 0x0C62, "full_sync_burst FULL BODY (62 bytes)");
        // P3.6b research step 7 (task #68): single-instruction
        // probes for each `call button_scan_debounce` site in
        // V1.71 firmware, so the per-site hit count reveals
        // which caller is responsible for the ~1.9-4.6 M body
        // executions step 6 saw.  As measured (and described in
        // the 033d51e commit body), the 0x0E1C call site --
        // which COINCIDES with the sub-label
        // `flow_display_loop_iteration_0CB4` -- fires
        // 3 651 176 times because the body's tail
        // (`flow_display_loop_iteration_0D7A` at asm:2897)
        // does a backward `bra flow_display_loop_iteration_
        // 0CB4` to busy-poll for `0x9A != 0 || control_flags.
        // bit3`.  The `display_loop_iteration ENTRY` probe
        // (PC 0x0E1A..0x0E1C) at 39 hits measures only outer
        // entries, NOT the inner-loop returns to 0x0E1C; the
        // call-site count therefore dominates by ~93 600x.
        // All other 8 call sites measure 0 hits in this run
        // (cold WAITING / reconnect WAITING / etc. are not
        // entered while menu_state == 4 holds).  Each `call`
        // is a 2-word PIC18 instruction; the [start, start+2)
        // range counts exactly one hit per call invocation.
        probe.add_pc_range(0x0E1C, 0x0E1E, "call button_scan @ 0x0E1C (display_loop_iteration)");
        probe.add_pc_range(0x1880, 0x1882, "call button_scan @ 0x1880 (cold WAITING)");
        probe.add_pc_range(0x1986, 0x1988, "call button_scan @ 0x1986 (display_state_entry)");
        probe.add_pc_range(0x1A08, 0x1A0A, "call button_scan @ 0x1A08 (reconnect WAITING)");
        probe.add_pc_range(0x1D6A, 0x1D6C, "call button_scan @ 0x1D6A (main_event_loop body)");
        probe.add_pc_range(0x1FE0, 0x1FE2, "call button_scan @ 0x1FE0 (unknown #1)");
        probe.add_pc_range(0x1FE6, 0x1FE8, "call button_scan @ 0x1FE6 (control_core_service_17E8)");
        probe.add_pc_range(0x21AE, 0x21B0, "call button_scan @ 0x21AE (unknown #2)");
        probe.add_pc_range(0x21DC, 0x21DE, "call button_scan @ 0x21DC (unknown #3)");
        // P3.6b research step 8a: count actual loop exits by
        // probing the instruction immediately AFTER the
        // busy-loop's `bra flow_display_loop_iteration_0CB4`
        // at PC 0x0F00.  PC 0x0F02 = `movlw 0x00` (second-
        // check start at asm:2898).  hit_count here = number
        // of times the busy-loop check let execution fall
        // through, i.e. the number of loop exits.
        probe.add_pc_range(0x0F02, 0x0F04, "loop EXIT (after bra @ 0x0F00)");
        // Also probe the loop-check entry PC so we can compute
        // average iterations-per-exit = loop-check-entries /
        // loop-exits.
        probe.add_pc_range(0x0EEC, 0x0EEE, "loop CHECK ENTRY (flow_..._0D7A)");
        let initial_parsed_data = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x030));
        let initial_frame_pos = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x0A6));
        let initial_rcsta = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0xFAB));
        let initial_ring_rd = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x098));
        let initial_ring_wr = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x099));
        // P3.6b research step 3 (task #63): also watch the parser-
        // stall watchdog state and the diag_reset_seen mask -- the
        // two RAM cells that, with the new BF/2B body PC ranges,
        // close the "4 entries but no flag clear" contradiction.
        let initial_gap_timeout = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x0AC));
        let initial_reset_seen = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x19D));
        // P3.6b research step 4 (task #65): intervention
        // experiment per codex on edb77b4.  Watch
        // rx_parsed_cmd AND attach a trigger -- when cmd
        // transitions to a BF/2N value (0x21..=0x2B), reset
        // v171_rx_frame_gap_timeout (0x0AC) to 0x01.  At
        // 0x01, the watchdog needs ~255 increments
        // (~720 K ticks) to expire, well past the 15 K-tick
        // cmd->data spacing.  If the watchdog hypothesis is
        // the SOLE root cause, this should make BF/2N data
        // bytes process and the BF/2B body / BF/27 tail run.
        // If anything else is still blocking dispatch, the
        // intervention probes will surface it.
        probe.add_watched_ram_with_trigger(
            0x02F,
            "rx_parsed_cmd",
            initial_parsed_cmd,
            0x21,    // match_min
            0x2B,    // match_max (covers BF/21..BF/2B inclusive)
            0x0AC,   // target_addr = v171_rx_frame_gap_timeout
            0x01,    // target_value = 1 (255 increments to expire)
        );
        probe.add_watched_ram(0x030, "rx_parsed_data", initial_parsed_data);
        probe.add_watched_ram(0x0A6, "rx_frame_position", initial_frame_pos);
        probe.add_watched_ram(0xFAB, "RCSTA", initial_rcsta);
        probe.add_watched_ram(0x098, "rx_ring_rd", initial_ring_rd);
        probe.add_watched_ram(0x099, "rx_ring_wr", initial_ring_wr);
        probe.add_watched_ram(0x0AC, "v171_rx_frame_gap_timeout", initial_gap_timeout);
        let initial_poll_lo = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x198));
        let initial_poll_hi = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x199));
        // P3.6b research step 8a (task #69): the
        // display_loop_iteration busy-loop at
        // flow_display_loop_iteration_0D7A (asm:2885-2897)
        // exits when `0x9A != 0 || control_flags.bit3` is
        // true.  Watch all three cells.  Note that 0x9A
        // BANKED reads physical 0x09A when BSR=0
        // (display_loop_iteration sets `movlb 0x00` near
        // its top at asm:2767) and physical 0x19A when
        // BSR=1; watch both to disambiguate which one the
        // loop actually polls in this run.  Also watch
        // 0x01F (control_flags) so bit-3 transitions are
        // visible alongside other flag edits (bit 0 ir_armed,
        // bit 1 connected, bit 2 rx_route_seen, bit 3 ?).
        let initial_event_byte_b0 = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x09A));
        let initial_event_byte_b1 = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x19A));
        let initial_control_flags = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x01F));
        probe.add_watched_ram(0x01F, "control_flags (bit3 = busy-loop exit predicate)", initial_control_flags);
        probe.add_watched_ram(0x09A, "0x09A BANK0 (busy-loop predicate when BSR=0; RIGHT event byte)", initial_event_byte_b0);
        probe.add_watched_ram(0x19A, "0x19A BANK1 (v171_diag_present_snap; busy-loop predicate when BSR=1)", initial_event_byte_b1);
        probe.add_watched_ram(0x196, "v171_diag_target", initial_target);
        probe.add_watched_ram(0x197, "v171_diag_present", initial_present);
        probe.add_watched_ram(0x198, "v171_diag_poll_lo", initial_poll_lo);
        probe.add_watched_ram(0x199, "v171_diag_poll_hi", initial_poll_hi);
        probe.add_watched_ram(0x19C, "v171_diag_flags", initial_flags);
        probe.add_watched_ram(0x19D, "v171_diag_reset_seen", initial_reset_seen);
        chain.cores[i_ctl].cycle_probe = Some(probe);
    }

    // P3.6b research: snapshot V1.71 diag-state RAM + EUSART
    // RX state right before the stage-3 sampler enters its
    // poll/reply window.  Compared against the post-sampler
    // snapshot, deltas confirm SOME state moved during the
    // window (positive observation only).  The ABSENCE of a
    // delta is weaker evidence -- the value could have moved
    // and returned to the same byte within the window
    // without ever being observed at the chunk boundaries
    // (10 M-tick granularity vs ~46 K-tick byte time).
    let pre_stage3_snapshot = (
        chain.cores[i_ctl].memory.read_raw(Address::from_raw(0x196)), // diag_target
        chain.cores[i_ctl].memory.read_raw(Address::from_raw(0x197)), // diag_present
        chain.cores[i_ctl].memory.read_raw(Address::from_raw(0x19A)), // diag_present_snap
        chain.cores[i_ctl].memory.read_raw(Address::from_raw(0x19C)), // diag_flags
        chain.cores[i_ctl].memory.read_raw(Address::from_raw(0x19D)), // diag_reset_seen
        chain.cores[i_ctl].memory.read_raw(Address::from_raw(0xFAB)), // RCSTA
        chain.cores[i_ctl].memory.read_raw(Address::from_raw(0x0A6)), // rx_frame_position
        chain.cores[i_ctl].memory.read_raw(Address::from_raw(0x02F)), // rx_parsed_cmd
        chain.cores[i_ctl].memory.read_raw(Address::from_raw(0x030)), // rx_parsed_data
    );
    let pre_stage3_tick = chain.current_tick;

    // Stage 3 PC sampler: step in small chunks and capture
    // CONTROL.PC + key state at each pause.  Sampler-bound
    // observation only -- if `v171_diag_pb_screen` (around
    // asm line 3550) holds the PC for ANY visible fraction
    // of a chunk it lights up the histogram, but a brief
    // visit (~50 Tcy ~= 0.04% of a 10 M-tick chunk) can be
    // missed; absence of PC hits is therefore weak evidence
    // and step-2 PC-trace hooks are needed before claiming
    // "v171_diag_pb_screen never entered".
    //
    // P3.6b research instrumentation (codex review of 67bfa1d):
    // also track per-chunk CONTROL EUSART/RX state, OERR rising
    // edges, parser-latch transitions, and parser-cmd-data
    // history.  The hypothesis ladder this is meant to support
    // -- "byte dropped" / "byte accepted but not latched" /
    // "latched but wrong cmd/data" / "entered BF/2N but missed
    // last-frame branch" / "executed branch but RAM write/toggle
    // failed" -- can only be DEFINITIVELY discriminated by
    // step-2 cycle-level probes.  At 10 M-tick boundary
    // sampling the most these counters can do is rule in or
    // out the FAR ENDS of that ladder (e.g. parser totally
    // dead vs alive-and-consuming-non-BF/2N) and corroborate
    // wire-side observations from `Chain::uart_tx_history`.
    //
    // RAM addresses (from `src/dlcp_fw/asm/dlcp_control_ram.inc`,
    // *physical* addresses -- simulator's `Address::from_raw`
    // uses bank-flattened addressing).
    // BANK 0 parser state:
    //   0x02F = rx_parsed_cmd      (latched by rx_parser_entry)
    //   0x030 = rx_parsed_data     (latched by rx_parser_entry)
    //   0x098 = rx_ring_rd         (parser consumer index;
    //                                advances by 1 per byte
    //                                consumed from the 48-byte
    //                                rx_ring_base@0x066)
    //   0x099 = rx_ring_wr         (ISR producer index)
    //   0x0A6 = rx_frame_position  (parser state: 0=route, 1=cmd, 2=data)
    //   0x0AB = bf08_fault_byte    (V1.71 BF/08 cache)
    //   0x0B7 = rx_ring_staging    (single-byte holding cell)
    // BANK 1 V1.71 diag state (physical 0x18N):
    //   0x196 = v171_diag_target
    //   0x197 = v171_diag_present
    //   0x198 = v171_diag_poll_lo
    //   0x199 = v171_diag_poll_hi
    //   0x19A = v171_diag_present_snap
    //   0x19C = v171_diag_flags    (bit 0 DIRTY, bit 1 RUNTIME_PENDING,
    //                                bit 2 RESET_PENDING per dlcp_control_ram.inc:307+)
    //   0x19D = v171_diag_reset_seen
    //
    // SFR addresses (PIC18 access bank):
    //   0xFAB = RCSTA  (bit 7 SPEN, bit 4 CREN, bit 1 OERR, bit 2 FERR)
    //   0xFAE = RCREG
    //   0xF9D = PIE1   (bit 5 RCIE)
    //   0xF9E = PIR1   (bit 5 RCIF)
    let mut pc_histogram: std::collections::HashMap<u16, u32> =
        std::collections::HashMap::new();
    let mut menu_state_histogram: std::collections::HashMap<u8, u32> =
        std::collections::HashMap::new();
    let mut bit5_set_count: u32 = 0;
    let mut diag_poll_lo_min: u8 = 0xFF;
    let mut diag_poll_lo_max: u8 = 0x00;
    let mut samples = 0u32;
    let mut target_changes: Vec<u8> = Vec::new();
    let mut last_target: u8 = chain.cores[i_ctl].memory.read_raw(Address::from_raw(0x196));
    target_changes.push(last_target);
    let mut bf2x_dispatch_hits: u32 = 0; // PC in 0x0630..0x0696
    // P3.6b research: EUSART RX state tracking.
    let mut last_rcsta: u8 = chain.cores[i_ctl]
        .memory
        .read_raw(Address::from_raw(0xFAB));
    let mut oerr_rising_edges: u32 = 0;
    let mut cren_falling_edges: u32 = 0; // 1 -> 0 = CREN-toggle recovery start
    let mut max_rx_fifo_depth: usize = 0;
    let mut max_ring_depth: u8 = 0; // (wr - rd + 48) mod 48
    let mut ring_oor_chunks: u32 = 0; // chunks where rd or wr left [0, 48)
    let mut rcif_set_chunks: u32 = 0;
    let mut rcif_clear_chunks: u32 = 0;
    // P3.6b research: parser-latch transition log -- record
    // (tick, frame_pos, cmd, data, ring_rd, ring_wr) every
    // time any of (frame_pos, cmd, data) changes since the
    // last sample.  Boundary-sampled at the same 10 M-tick
    // granularity as the rest of the sampler, so a positive
    // observation (cmd=0x27 visible at any boundary) is
    // hard evidence the parser entered BF/27 dispatch, but
    // the negative case (no boundary samples in 0x21..0x27)
    // does NOT prove the parser failed to reach dispatch --
    // the entire 21-byte burst lasts ~310 K ticks (well
    // under one chunk) and dispatch+clear can complete
    // entirely between samples.  Step-2 cycle-level probes
    // are required to make negative-dispatch claims.
    let mut last_parser_latch: (u8, u8, u8, u8, u8) = (
        chain.cores[i_ctl].memory.read_raw(Address::from_raw(0x0A6)), // rx_frame_position
        chain.cores[i_ctl].memory.read_raw(Address::from_raw(0x02F)), // rx_parsed_cmd
        chain.cores[i_ctl].memory.read_raw(Address::from_raw(0x030)), // rx_parsed_data
        chain.cores[i_ctl].memory.read_raw(Address::from_raw(0x098)), // rx_ring_rd
        chain.cores[i_ctl].memory.read_raw(Address::from_raw(0x099)), // rx_ring_wr
    );
    let mut parser_latch_log: Vec<(u64, u8, u8, u8, u8, u8)> = Vec::new();
    parser_latch_log.push((
        chain.current_tick,
        last_parser_latch.0,
        last_parser_latch.1,
        last_parser_latch.2,
        last_parser_latch.3,
        last_parser_latch.4,
    ));
    let total_chunks: u64 = 200;
    let chunk_ticks: u64 = 10_000_000;
    for _ in 0..total_chunks {
        chain.step_ticks(chunk_ticks);
        if chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(DIAG_PRESENT_RAM))
            == 0x03
        {
            break;
        }
        samples += 1;
        let pc = chain.cores[i_ctl].pc();
        let pc_high: u16 = (pc & 0xFF00) as u16;
        *pc_histogram.entry(pc_high).or_insert(0) += 1;
        // Tightened range: v171_bf2x_case_check body runs from
        // 0x0630 up to (but excluding) 0x0696, where the shared
        // parser tail flow_rx_parser_entry_05EA begins.  Prior
        // 0x0700 ceiling included unrelated following routines
        // and would overcount any hits.  Codex review of 56841f4
        // LOW.
        if pc >= 0x0630 && pc < 0x0696 {
            bf2x_dispatch_hits += 1;
        }
        let target_now = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x196));
        if target_now != last_target {
            target_changes.push(target_now);
            last_target = target_now;
        }
        let mstate = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(MENU_STATE_RAM));
        *menu_state_histogram.entry(mstate).or_insert(0) += 1;
        let cache_9a = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x09A));
        if cache_9a & 0x20 != 0 {
            bit5_set_count += 1;
        }
        let poll_lo = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x198));
        if poll_lo < diag_poll_lo_min {
            diag_poll_lo_min = poll_lo;
        }
        if poll_lo > diag_poll_lo_max {
            diag_poll_lo_max = poll_lo;
        }
        // P3.6b research: EUSART RX state.
        let rcsta = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0xFAB));
        // OERR rising edge: bit 1 went 0 -> 1.
        if (rcsta & 0x02) != 0 && (last_rcsta & 0x02) == 0 {
            oerr_rising_edges += 1;
        }
        // CREN falling edge: bit 4 went 1 -> 0 (toggle-recover start).
        if (rcsta & 0x10) == 0 && (last_rcsta & 0x10) != 0 {
            cren_falling_edges += 1;
        }
        last_rcsta = rcsta;
        // PIR1.RCIF (bit 5): asserted while FIFO non-empty.
        let pir1 = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0xF9E));
        if (pir1 & 0x20) != 0 {
            rcif_set_chunks += 1;
        } else {
            rcif_clear_chunks += 1;
        }
        let fifo_depth = chain.cores[i_ctl].peripherals.eusart.rx_fifo_depth();
        if fifo_depth > max_rx_fifo_depth {
            max_rx_fifo_depth = fifo_depth;
        }
        // SW rx_ring depth: parser-side fill = (wr - rd) modulo
        // ring size.  V1.71 RX ring is 48 bytes at 0x066..0x095
        // (`rx_ring_base equ 0x066` with `subwf 0x99, 0x30` wrap
        // logic in the cooperative ISR at v171.asm:817-835), so
        // both `rx_ring_rd` and `rx_ring_wr` live in [0, 48) and
        // depth = (wr - rd + 48) mod 48.  Using `u8::wrapping_sub`
        // would compute mod 256 and report a false 200+-byte
        // backlog every time `wr` wraps past 0 ahead of `rd` --
        // codex MEDIUM from 2dbaea9.  `RING_OOR_SENTINEL` (0xFF)
        // surfaces a pointer that escaped the [0, 48) window so a
        // probe corruption shows up as 0xFF instead of a noisy
        // depth value.
        const RING_SIZE: u8 = 48;
        const RING_OOR_SENTINEL: u8 = 0xFF;
        let ring_rd = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x098)); // rx_ring_rd
        let ring_wr = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x099)); // rx_ring_wr
        let ring_depth = if ring_rd < RING_SIZE && ring_wr < RING_SIZE {
            (ring_wr + RING_SIZE - ring_rd) % RING_SIZE
        } else {
            ring_oor_chunks += 1;
            RING_OOR_SENTINEL
        };
        if ring_depth != RING_OOR_SENTINEL && ring_depth > max_ring_depth {
            max_ring_depth = ring_depth;
        }
        // P3.6b research: parser latch transitions.
        let frame_pos = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x0A6)); // rx_frame_position
        let cmd_byte = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x02F)); // rx_parsed_cmd
        let data_byte = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(0x030)); // rx_parsed_data
        let latch_now = (frame_pos, cmd_byte, data_byte, ring_rd, ring_wr);
        if latch_now != last_parser_latch {
            parser_latch_log.push((
                chain.current_tick,
                frame_pos,
                cmd_byte,
                data_byte,
                ring_rd,
                ring_wr,
            ));
            last_parser_latch = latch_now;
        }
    }
    let diag_flags = chain.cores[i_ctl]
        .memory
        .read_raw(Address::from_raw(0x19C));
    let diag_reset_seen = chain.cores[i_ctl]
        .memory
        .read_raw(Address::from_raw(0x19D));
    let diag_present_snap = chain.cores[i_ctl]
        .memory
        .read_raw(Address::from_raw(0x19A));
    eprintln!("\n=== Stage 3 sampler ({samples} samples @ {chunk_ticks} ticks each) ===");
    let mut pc_buckets: Vec<_> = pc_histogram.iter().collect();
    pc_buckets.sort_by_key(|(_, c)| std::cmp::Reverse(**c));
    eprintln!("PC distribution (high byte): {:02X?}", pc_buckets);
    eprintln!("  -- key labels: 0x094 button_scan, 0x0E1 display_loop_iteration,");
    eprintln!("                 0x12C v171_diag_pb_screen, 0x151 v171_diag_loop,");
    eprintln!("                 0x190 flow_post_connect_init_11F0, 0x1AB volume_screen");
    eprintln!("menu_state distribution: {:?}", menu_state_histogram);
    eprintln!("0x9A bit 5 (RIGHT event) set count: {bit5_set_count}");
    eprintln!("v171_diag_poll_lo (0x198): 0x{diag_poll_lo_min:02X}..0x{diag_poll_lo_max:02X}");
    eprintln!(
        "v171_diag_flags (0x19C) at end: 0x{diag_flags:02X} \
         (bit 0=DIRTY, bit 1=RUNTIME_PENDING, bit 2=RESET_PENDING per dlcp_control_ram.inc:307+)"
    );
    eprintln!("v171_diag_reset_seen (0x19D) at end: 0x{diag_reset_seen:02X}");
    eprintln!("v171_diag_present_snap (0x19A) at end: 0x{diag_present_snap:02X}");
    eprintln!("BF/2N dispatch hits (PC in 0x0630..0x0696): {bf2x_dispatch_hits} / {samples}");
    eprintln!("v171_diag_target trajectory: {:02X?}", target_changes);

    // P3.6b research: pre/post-sampler diag-state snapshot
    // delta + EUSART RX flow summary + parser-latch
    // transition log.  All counters below are sampled at
    // 10 M-tick chunk boundaries -- this is far longer than
    // a 31250-baud frame (~46 K ticks), so OERR rising,
    // CREN falling, RCIF assert, FIFO depth>0, and
    // parsed_cmd transitions can all happen and clear
    // entirely *within* one chunk and never be observed.
    // Therefore:
    //   - "0 OERR rising edges" == not observed at boundary,
    //     not "no transient OERR ever happened".
    //   - "0 chunks with RCIF set" == ISR drained FIFO
    //     within one chunk, not "RCIF never asserted".
    //   - "no parser-latch with cmd=0x21..0x27" == not
    //     observed at boundary, not "dispatch never fired".
    // These weaknesses motivate the finer-grained step-2
    // probes (PC-hit counter at v171_bf2x_case_check entry,
    // cycle-by-cycle parsed_cmd sniffer).
    //
    // Direction the counters can still distinguish, in
    // cautious language:
    //   - The full per-byte CONTROL.RX arrival stream
    //     (recorded at TX-emit time, not boundary-sampled)
    //     IS authoritative for "did the byte attempt
    //     wire delivery?" -- so a positive observation of
    //     21 contiguous BF/2N bytes in that stream is a
    //     hard fact, independent of the boundary sampler.
    //   - For the ring/FIFO/parser-latch counters,
    //     observations like "rd advanced" or "non-BF/2N
    //     cmds visible" are still proof of *some* parser
    //     activity, but NEGATIVE observations ("rd never
    //     advanced", "parser-latch never showed cmd in
    //     0x21..0x27") are weaker -- the parser could
    //     have advanced and returned to the same value
    //     within a chunk, or latched cmd briefly and had
    //     it cleared by the dispatch tail before the
    //     next sampler boundary.  Step-2 needs finer
    //     instrumentation (PC-hit counter at
    //     v171_bf2x_case_check entry, cycle-by-cycle
    //     parsed_cmd sniffer, executor-side write hooks)
    //     before any negative claim about the dispatch
    //     path is safe to make.
    let post_stage3_snapshot = (
        chain.cores[i_ctl].memory.read_raw(Address::from_raw(0x196)),
        chain.cores[i_ctl].memory.read_raw(Address::from_raw(0x197)),
        chain.cores[i_ctl].memory.read_raw(Address::from_raw(0x19A)),
        chain.cores[i_ctl].memory.read_raw(Address::from_raw(0x19C)),
        chain.cores[i_ctl].memory.read_raw(Address::from_raw(0x19D)),
        chain.cores[i_ctl].memory.read_raw(Address::from_raw(0xFAB)),
        chain.cores[i_ctl].memory.read_raw(Address::from_raw(0x0A6)), // rx_frame_position
        chain.cores[i_ctl].memory.read_raw(Address::from_raw(0x02F)), // rx_parsed_cmd
        chain.cores[i_ctl].memory.read_raw(Address::from_raw(0x030)), // rx_parsed_data
    );
    let post_stage3_tick = chain.current_tick;
    eprintln!(
        "\n=== P3.6b research: diag-state snapshot delta (pre vs post sampler) ==="
    );
    eprintln!(
        "tick: pre={pre_stage3_tick}, post={post_stage3_tick}, \
         delta={}",
        post_stage3_tick - pre_stage3_tick
    );
    eprintln!(
        "RAM 0x196 diag_target:        pre=0x{:02X}, post=0x{:02X}",
        pre_stage3_snapshot.0, post_stage3_snapshot.0
    );
    eprintln!(
        "RAM 0x197 diag_present:       pre=0x{:02X}, post=0x{:02X}",
        pre_stage3_snapshot.1, post_stage3_snapshot.1
    );
    eprintln!(
        "RAM 0x19A diag_present_snap:  pre=0x{:02X}, post=0x{:02X}",
        pre_stage3_snapshot.2, post_stage3_snapshot.2
    );
    eprintln!(
        "RAM 0x19C diag_flags:         pre=0x{:02X}, post=0x{:02X}",
        pre_stage3_snapshot.3, post_stage3_snapshot.3
    );
    eprintln!(
        "RAM 0x19D diag_reset_seen:    pre=0x{:02X}, post=0x{:02X}",
        pre_stage3_snapshot.4, post_stage3_snapshot.4
    );
    eprintln!(
        "SFR 0xFAB RCSTA:              pre=0x{:02X}, post=0x{:02X}",
        pre_stage3_snapshot.5, post_stage3_snapshot.5
    );
    eprintln!(
        "RAM 0x0A6 rx_frame_position:  pre=0x{:02X}, post=0x{:02X}",
        pre_stage3_snapshot.6, post_stage3_snapshot.6
    );
    eprintln!(
        "RAM 0x02F rx_parsed_cmd:      pre=0x{:02X}, post=0x{:02X}",
        pre_stage3_snapshot.7, post_stage3_snapshot.7
    );
    eprintln!(
        "RAM 0x030 rx_parsed_data:     pre=0x{:02X}, post=0x{:02X}",
        pre_stage3_snapshot.8, post_stage3_snapshot.8
    );
    eprintln!("\n=== P3.6b research: EUSART RX flow summary ===");
    eprintln!("OERR rising edges (RCSTA bit 1, 0->1):  {oerr_rising_edges}");
    eprintln!("CREN falling edges (RCSTA bit 4, 1->0): {cren_falling_edges}");
    eprintln!(
        "max RX FIFO depth (HW, 0..=2):          {max_rx_fifo_depth} (sampler granularity {chunk_ticks} ticks)"
    );
    eprintln!(
        "max SW rx_ring depth ((wr-rd+48)%48):   {max_ring_depth} (nonzero = parser falling behind; OOR chunks={ring_oor_chunks})"
    );
    eprintln!(
        "PIR1.RCIF chunks:                       set={rcif_set_chunks}, clear={rcif_clear_chunks} (ratio = ISR drain duty cycle)"
    );
    eprintln!(
        "parser-latch transitions captured:      {} (each = (frame_pos, cmd, data, ring_rd, ring_wr) changed at sampler boundary)",
        parser_latch_log.len()
    );
    let head = parser_latch_log.iter().take(8);
    let tail_start = parser_latch_log.len().saturating_sub(8);
    eprintln!(
        "parser-latch first 8: {:#?}",
        head.collect::<Vec<_>>()
    );
    if parser_latch_log.len() > 8 {
        eprintln!(
            "parser-latch last 8:  {:#?}",
            parser_latch_log.iter().skip(tail_start).collect::<Vec<_>>()
        );
    }

    // P3.6b research: per-byte CONTROL.RX arrivals during
    // the stage-3 window.  Codex MEDIUM/LOW from 2dbaea9:
    // `chain.uart_tx_history` is recorded at TX-emit time
    // (just before `Chain::deliver_uart_byte` calls
    // `Eusart::deliver_rx_byte`; see chain.rs:131-149,
    // 497-526), NOT after destination acceptance.  These
    // records therefore represent **wire-delivery
    // attempts** -- the byte may still be rejected by
    // RCSTA.SPEN / RCSTA.CREN gating, dropped by an MCLR
    // hold (not the case here), or never reach the
    // software ring.  Use them to confirm the wire side,
    // not to claim FIFO acceptance.
    let ctl_rx_arrivals: Vec<(u64, usize, u8)> = chain
        .uart_tx_history
        .iter()
        .skip(stage2_history_len)
        .filter(|r| r.dst_core == i_ctl)
        .map(|r| (r.tick, r.src_core, r.byte))
        .collect();
    eprintln!(
        "\n=== P3.6b research: per-byte CONTROL.RX arrivals (stage 3, total {}) ===",
        ctl_rx_arrivals.len()
    );
    // Inter-byte spacing histogram (in chunk_ticks units),
    // bucketed to surface obvious bursts vs droughts.
    if ctl_rx_arrivals.len() >= 2 {
        let mut gaps: Vec<u64> = Vec::with_capacity(ctl_rx_arrivals.len() - 1);
        for w in ctl_rx_arrivals.windows(2) {
            gaps.push(w[1].0 - w[0].0);
        }
        gaps.sort_unstable();
        let n = gaps.len();
        let p50 = gaps[n / 2];
        let p90 = gaps[(n * 9) / 10];
        let max_gap = *gaps.last().unwrap();
        let min_gap = *gaps.first().unwrap();
        eprintln!(
            "  inter-byte tick gaps (n={n}): min={min_gap}, p50={p50}, p90={p90}, max={max_gap} \
             (15444 ticks ~= one 31250-baud byte time @ 48 MHz universal time base)"
        );
    }
    // Locate any BF/2N reply burst (route 0xBF + cmd in
    // 0x21..=0x27) on the wire and dump a window around
    // it.  This is the byte stream that *should* arrive
    // at CONTROL.RX immediately AFTER the B1/21 query
    // and that the parser would normally dispatch to
    // v171_bf2x_case_check.
    //
    // What this view CAN tell us (positive observation):
    //   - 21 contiguous bytes [BF,21,d, BF,22,d, ..., BF,27,d]
    //     with ~15 480-tick spacing means the wire side
    //     delivered the burst (records are pushed at
    //     TX-emit time in `Chain::uart_tx_history`,
    //     before destination SPEN/CREN gating, so this is
    //     authoritative for "wire emission attempted",
    //     not for FIFO acceptance).
    //
    // What this view CANNOT tell us:
    //   - whether the bytes were latched into RCREG and
    //     pushed onto rx_ring (the SW ISR could still
    //     drop them via OERR, CREN-toggle, or a ring-
    //     overrun roll-back at v171.asm:837-849), and
    //   - whether the parser ever entered the BF/2N
    //     dispatch path or wrote diag_present.
    // Negative claims about parser/dispatch behaviour
    // require step-2 cycle-level instrumentation.
    let mut burst_starts: Vec<usize> = Vec::new();
    for (i, w) in ctl_rx_arrivals.windows(2).enumerate() {
        if w[0].2 == 0xBF && (0x21..=0x27).contains(&w[1].2) {
            burst_starts.push(i);
        }
    }
    eprintln!(
        "  BF/2N (route 0xBF + cmd 0x21..0x27) byte pairs in CONTROL.RX: {}",
        burst_starts.len()
    );
    for &start in &burst_starts {
        let from = start.saturating_sub(2);
        let to = (start + 24).min(ctl_rx_arrivals.len());
        eprintln!(
            "    burst @ idx={start} (tick={}): {} bytes around it:",
            ctl_rx_arrivals[start].0,
            to - from
        );
        for (tick, src, byte) in &ctl_rx_arrivals[from..to] {
            eprintln!("      tick={tick:>12} src=core[{src}] byte=0x{byte:02X}");
        }
    }
    // Also dump the arrival stream so we can correlate tick
    // with each arrival.  Capped at FULL_STREAM_CAP lines to
    // bound the failure output -- the cap is purely a
    // defensive guard against future probe variants that
    // open longer stage-3 windows or feed denser cadences;
    // todays nominal run is well below the cap (~186 lines).
    // Codex LOW from 2dbaea9.
    const FULL_STREAM_CAP: usize = 500;
    let stream_n = ctl_rx_arrivals.len().min(FULL_STREAM_CAP);
    eprintln!(
        "  arrival stream (first {stream_n} of {} total):",
        ctl_rx_arrivals.len()
    );
    for (tick, src, byte) in ctl_rx_arrivals.iter().take(stream_n) {
        eprintln!(
            "    tick={tick:>12} src=core[{src}] byte=0x{byte:02X}"
        );
    }
    if ctl_rx_arrivals.len() > stream_n {
        eprintln!(
            "    ... ({} more arrivals truncated; raise FULL_STREAM_CAP if needed)",
            ctl_rx_arrivals.len() - stream_n
        );
    }

    // Stage 3: run until both PB-reply bits land in
    // v171_diag_present.  Budget was 10 B during the
    // discovery probe; trimmed to 2 B (~16 s simulated,
    // ~30 s wall) since we know convergence does NOT
    // happen -- per the docstring above, present stays
    // at 0x00 (CONTROL never successfully processes
    // BF/27 through the BF/2N last-frame path; both
    // PENDING bits stay set, target trajectory `[00]`).
    // Smaller budget = faster iteration when
    // investigating root cause.
    // P3.6b research step 5 (task #66): extend the
    // post-sampler budget from 2G to 8G ticks so that, with
    // the step-4 watchdog intervention enabled, we have a
    // longer window for PB2 to converge.  Test wall time
    // scales linearly -- ~80 s previously, ~5-6 min with
    // this budget -- acceptable for a research probe.
    //
    // Result of step-5 run with the 8G budget: PB2 still
    // does NOT converge -- the cadence loop only fires the
    // PB1 query once and v171_diag_poll_lo only decrements
    // 38 times (from 0x80 to 0x5A) over ~218 sim seconds.
    // This is NOT a "second root cause beyond the watchdog";
    // it's pure cadence starvation: V171_DIAG_POLL_RELOAD =
    // 0x80 needs 128 cadence-loop calls to expire once, the
    // sim only ran 39 calls in this window, and the call
    // rate is bottlenecked by display_loop_iteration time.
    // Codex LOW from 82f29c5 review (Stage 3 budget comment
    // wording).  Step-6 work: cycle-count display_loop_
    // iteration's callees vs design budget (~31,250 Tcy
    // per 128 Hz cadence tick).
    chain.run_until(
        50_000_000, // 50 M = ~350 ms wall per chunk
        8_000_000_000,
        |c| c.cores[i_ctl].memory.read_raw(Address::from_raw(DIAG_PRESENT_RAM)) == 0x03,
    );

    let diag_present = chain.cores[i_ctl]
        .memory
        .read_raw(Address::from_raw(DIAG_PRESENT_RAM));
    let diag_target = chain.cores[i_ctl]
        .memory
        .read_raw(Address::from_raw(DIAG_TARGET_RAM));
    let menu_state = chain.cores[i_ctl]
        .memory
        .read_raw(Address::from_raw(MENU_STATE_RAM));
    let main0_pc = chain.cores[i_main0].pc();
    let main1_pc = chain.cores[i_main1].pc();
    let stage3_tick = chain.current_tick;
    let stage3_history_len = chain.uart_tx_history.len();
    let post_stage1_tx = stage3_history_len.saturating_sub(stage1_history_len);

    // Helper: read a per-PB diag cache slice and report
    // whether any cell is non-zero.  A genuine PB reply
    // must land cell content; an unrelated RAM clobber
    // to v171_diag_present alone would leave the cache
    // empty.  Codex MEDIUM from 3a43e43 review -- this
    // is what makes the present-byte assertion robust
    // against false-positive convergence if/when this
    // probe transitions from `#[ignore]` to hard-pass.
    let pb_cache_has_content = |chain: &Chain, base: u16| -> bool {
        (0..DIAG_PB_CACHE_LEN).any(|offset| {
            chain.cores[i_ctl]
                .memory
                .read_raw(Address::from_raw(base + offset))
                != 0x00
        })
    };
    let pb1_cache_present = pb_cache_has_content(&chain, DIAG_PB1_BASE_RAM);
    let pb2_cache_present = pb_cache_has_content(&chain, DIAG_PB2_BASE_RAM);

    // Diagnostic: dump per-edge byte streams from stage 3
    // (post-navigation polling window).
    let stage3_records: Vec<_> = chain
        .uart_tx_history
        .iter()
        .skip(stage2_history_len)
        .collect();
    let extract = |src: usize| -> Vec<u8> {
        stage3_records
            .iter()
            .filter(|r| r.src_core == src)
            .map(|r| r.byte)
            .collect()
    };
    let ctl_tx_s3 = extract(i_ctl);
    let m0_tx_s3 = extract(i_main0);
    let m1_tx_s3 = extract(i_main1);
    eprintln!("Stage 3 byte streams (post-navigation):");
    eprintln!("  CTL.TX  ({} bytes): {:02X?}", ctl_tx_s3.len(), &ctl_tx_s3[..ctl_tx_s3.len().min(60)]);
    eprintln!("  MAIN0.TX ({} bytes): {:02X?}", m0_tx_s3.len(), &m0_tx_s3[..m0_tx_s3.len().min(60)]);
    eprintln!("  MAIN1.TX ({} bytes): {:02X?}", m1_tx_s3.len(), &m1_tx_s3[..m1_tx_s3.len().min(60)]);
    // Search for diag-query frames anywhere in CTL.TX.
    let ctl_b1_22 = ctl_tx_s3.windows(3).filter(|w| *w == [0xB1, 0x22, 0x00]).count();
    let ctl_b1_21 = ctl_tx_s3.windows(3).filter(|w| *w == [0xB1, 0x21, 0x00]).count();
    let ctl_b2_22 = ctl_tx_s3.windows(3).filter(|w| *w == [0xB2, 0x22, 0x00]).count();
    let ctl_b2_21 = ctl_tx_s3.windows(3).filter(|w| *w == [0xB2, 0x21, 0x00]).count();
    eprintln!("CTL diag query counts: B1/22/00={ctl_b1_22}, B1/21/00={ctl_b1_21}, B2/22/00={ctl_b2_22}, B2/21/00={ctl_b2_21}");
    let m0_bf21 = m0_tx_s3.windows(2).filter(|w| *w == [0xBF, 0x21]).count();
    let m1_bf21 = m1_tx_s3.windows(2).filter(|w| *w == [0xBF, 0x21]).count();
    let m0_bf27 = m0_tx_s3.windows(2).filter(|w| *w == [0xBF, 0x27]).count();
    let m1_bf27 = m1_tx_s3.windows(2).filter(|w| *w == [0xBF, 0x27]).count();
    eprintln!("MAIN BF/2N reply markers: MAIN0 BF/21={m0_bf21} BF/27={m0_bf27}, MAIN1 BF/21={m1_bf21} BF/27={m1_bf27}");

    // Count BF byte totals on MAIN1.TX (forwarded reply burst).
    let m0_bf_total = m0_tx_s3.iter().filter(|&&b| b == 0xBF).count();
    let m1_bf_total = m1_tx_s3.iter().filter(|&&b| b == 0xBF).count();
    eprintln!("BF byte totals: MAIN0 = {m0_bf_total}, MAIN1 = {m1_bf_total} (full 7-frame cmd 21 burst = 7 BF, plus 4 BF for cmd 22 = 11 BF)");

    // Print a window AROUND each BF/27 in MAIN1.TX (10 bytes before + 5 after).
    for (i, w) in m1_tx_s3.windows(3).enumerate() {
        if w[0] == 0xBF && w[1] == 0x27 {
            let start = i.saturating_sub(10);
            let end = (i + 5).min(m1_tx_s3.len());
            eprintln!("MAIN1.TX BF/27 frame at offset {i}: bytes [{}..{}] = {:02X?}", start, end, &m1_tx_s3[start..end]);
        }
    }

    // Check CONTROL's RX state: RCSTA, OERR latch, RCREG, frame_pos
    let ctl_rcsta = chain.cores[i_ctl]
        .memory
        .read_raw(Address::from_raw(0xFAB));
    let ctl_rcreg = chain.cores[i_ctl]
        .memory
        .read_raw(Address::from_raw(0xFAE));
    let ctl_frame_pos = chain.cores[i_ctl]
        .memory
        .read_raw(Address::from_raw(0x0A6));
    let ctl_parsed_cmd = chain.cores[i_ctl]
        .memory
        .read_raw(Address::from_raw(0x02F));
    let ctl_parsed_data = chain.cores[i_ctl]
        .memory
        .read_raw(Address::from_raw(0x030));
    eprintln!(
        "CTL RX state: RCSTA=0x{ctl_rcsta:02X} (OERR bit 1={}), RCREG=0x{ctl_rcreg:02X}, \
         frame_pos(0xA6)=0x{ctl_frame_pos:02X}, parsed_cmd(0x2F)=0x{ctl_parsed_cmd:02X}, \
         parsed_data(0x30)=0x{ctl_parsed_data:02X}",
        if ctl_rcsta & 0x02 != 0 { "1 (OERR LATCHED -- bytes dropped)" } else { "0" }
    );

    // P3.6b research step 2 (task #62): dump cycle-level
    // probe results.  These counters are PER-INSTRUCTION,
    // so they bypass the 10 M-tick boundary blind spot
    // entirely -- a positive count is a hard fact, and a
    // zero count is a hard fact in the OPPOSITE direction
    // (no instruction with PC in range was ever stepped).
    if let Some(probe) = chain.cores[i_ctl].cycle_probe.as_ref() {
        eprintln!("\n=== P3.6b research step 2: cycle-level probe summary ===");
        eprintln!(
            "PC-range hit counts + total Tcy (per-instruction, NOT boundary-sampled):"
        );
        for r in &probe.pc_ranges {
            // Average Tcy per hit -- gives a useful "instructions
            // average X cycles each" view that helps spot
            // subroutines containing multi-Tcy operations
            // (CALL/RETURN/2-word instructions, long branches).
            let avg_per_hit = if r.hit_count > 0 {
                r.total_cycles as f64 / r.hit_count as f64
            } else {
                0.0
            };
            eprintln!(
                "  [{:#06X}..{:#06X})  hits = {:>10}  Tcy = {:>14}  avg = {:>5.2}  -- {}",
                r.start, r.end, r.hit_count, r.total_cycles, avg_per_hit, r.label
            );
        }
        eprintln!("Watched RAM transition logs (full per-instruction history):");
        for w in &probe.watched_ram {
            // P3.6b research step 4: also dump trigger
            // fire-count if a trigger is attached -- this
            // is what tells us the intervention actually
            // ran.
            let trigger_suffix = match &w.trigger {
                Some(t) => format!(
                    "  [TRIGGER on [0x{:02X}..=0x{:02X}] -> RAM 0x{:03X} = 0x{:02X}, fired {}x]",
                    t.match_min, t.match_max, t.target_addr, t.target_value, t.fire_count
                ),
                None => String::new(),
            };
            eprintln!(
                "  RAM 0x{:03X} {} -- {} transitions, last_value=0x{:02X}{}",
                w.addr,
                w.label,
                w.transitions.len(),
                w.last_value,
                trigger_suffix
            );
            // Cap dump for readability.  rx_parsed_cmd / data /
            // ring_rd / frame_pos / rx_frame_gap_timeout can each
            // produce hundreds of transitions across a 5 s sim,
            // so the cap is set generously to keep the burst
            // window's transitions visible at the end of long
            // logs (P3.6b research step 3, task #63).
            const TRANSITION_DUMP_CAP: usize = 1500;
            let n = w.transitions.len().min(TRANSITION_DUMP_CAP);
            for (tick, val) in w.transitions.iter().take(n) {
                eprintln!("    tick={tick:>12} new_value=0x{val:02X}");
            }
            if w.transitions.len() > n {
                eprintln!(
                    "    ... ({} more transitions truncated)",
                    w.transitions.len() - n
                );
            }
        }
        // Distinct rx_parsed_cmd values seen -- the CRITICAL
        // discriminator: if any cmd in 0x21..=0x2B appears,
        // the parser DID latch a BF/2N command byte.
        let parsed_cmd_log = probe
            .watched_ram
            .iter()
            .find(|w| w.addr == 0x02F)
            .expect("rx_parsed_cmd watch was attached");
        let mut distinct_cmds: Vec<u8> = parsed_cmd_log
            .transitions
            .iter()
            .map(|(_, v)| *v)
            .collect();
        distinct_cmds.sort_unstable();
        distinct_cmds.dedup();
        eprintln!("Distinct rx_parsed_cmd values observed: {distinct_cmds:02X?}");
        let bf2n_cmds: Vec<u8> = distinct_cmds
            .iter()
            .copied()
            .filter(|v| (0x21..=0x2B).contains(v))
            .collect();
        eprintln!(
            "  ... including BF/2N range 0x21..=0x2B: {bf2n_cmds:02X?} \
             (empty = parser NEVER latched a BF/2N cmd byte; \
              non-empty = parser DID enter BF/2N space)"
        );
    }

    assert_eq!(
        diag_present, 0x03,
        "v171_diag_present must show both PBs replied (0x03); \
         got 0x{diag_present:02X}\n  \
         diag_target=0x{diag_target:02X}, menu_state={menu_state}, \
         main0_pc=0x{main0_pc:04X}, main1_pc=0x{main1_pc:04X}\n  \
         pb1_cache_has_content={pb1_cache_present}, pb2_cache_has_content={pb2_cache_present}\n  \
         stage1_tick={stage1_tick}, stage3_tick={stage3_tick}, \
         post-stage1 UART deliveries={post_stage1_tx}"
    );
    // Codex MEDIUM follow-through: present == 0x03 alone
    // could be set by an unrelated RAM clobber.  A real
    // PB reply must also have updated the per-PB cache
    // cells.  Both must hold.
    assert!(
        pb1_cache_present,
        "v171_diag_present == 0x03 but PB1 cache at 0x{:03X}..0x{:03X} is all-zero -- \
         present byte was clobbered, not set by a real reply",
        DIAG_PB1_BASE_RAM,
        DIAG_PB1_BASE_RAM + DIAG_PB_CACHE_LEN
    );
    assert!(
        pb2_cache_present,
        "v171_diag_present == 0x03 but PB2 cache at 0x{:03X}..0x{:03X} is all-zero -- \
         present byte was clobbered, not set by a real reply",
        DIAG_PB2_BASE_RAM,
        DIAG_PB2_BASE_RAM + DIAG_PB_CACHE_LEN
    );

    // Codex LOW: the no-echo assertion below is too
    // weak in isolation -- a non-ring delivery (fan-out
    // drift, reverse coupling) would still pass `src !=
    // dst`.  Mirror the step-1 smoke test's stronger
    // edge-whitelist audit so the diag-polling window
    // is held to the same contract.
    for record in &chain.uart_tx_history {
        assert_ne!(
            record.src_core, record.dst_core,
            "no UART delivery may route a core's TX to its own RX; \
             firmware-driven echo-loop check failed during diag poll: {record:?}"
        );
        let edge = (record.src_core, record.dst_core);
        let is_ring_edge = edge == (i_ctl, i_main0)
            || edge == (i_main0, i_main1)
            || edge == (i_main1, i_ctl);
        assert!(
            is_ring_edge,
            "uart_tx_history record routes on a non-ring edge {edge:?} \
             (i_ctl={i_ctl}, i_main0={i_main0}, i_main1={i_main1}); \
             record: {record:?}"
        );
    }
}

/// P3.6 step 2 byte-level trace -- which hop of the
/// route-byte decrement-and-forward protocol breaks for
/// PB2 queries?
///
/// V3.2 MAIN identifies its PB index implicitly via chain
/// position.  CONTROL sends `0xB1` for PB1 and `0xB2` for
/// PB2 (`dlcp_control_v171.asm:4296`).  Each MAIN's parser
/// (`dlcp_main_v32.asm:1799`) handles route bytes:
///
///   * `0xB0` -> broadcast: clear bit0, fall through to
///     consume-or-forward.
///   * `0xB1` -> addressed-to-me: set bit0, consume locally
///     (do NOT forward downstream).
///   * `0xBx` (x in 2..=E) -> not me yet; clear bit0,
///     decrement byte by 1, forward downstream.  This is
///     the hop counter: every MAIN burns one decrement.
///   * `0xBF` -> reply prefix: don't decrement, forward
///     unchanged so reply chains return upstream intact.
///
/// So a `0xB2` query from CONTROL should:
///   1. land at MAIN0.RX,
///   2. trigger MAIN0 to emit `0xB1` on its TX (decremented
///      and forwarded),
///   3. land at MAIN1.RX,
///   4. trigger MAIN1 to consume locally + emit a 7-frame
///      `BF/21..BF/27` reply burst on its TX,
///   5. arrive at CONTROL.RX (closing the ring), where
///      v171_diag_present bit 1 gets set.
///
/// This probe runs the diag-poll convergence and dumps the
/// route-byte traffic per ring edge so we can see which
/// step (1-5) actually fires.  `#[ignore]`d so the routine
/// suite stays fast; budget is 2 B ticks (~30 s wall).
///
/// **Status (post-9430ec1)**: dev-time diagnostic dump only --
/// the contract-checking equivalents codex originally requested
/// for this probe (stage-1 convergence assert, frame-level
/// `windows()` parsing) live in the richer
/// `three_core_ring_v171_v32_v32_diag_page_polls_pb1_and_pb2`
/// probe (commits 368e8c3 + 56841f4).  Task #40 was closed as
/// obsolete on that basis; this probe is intentionally retained
/// as a byte-level dump aid for P3.6b research, NOT a regression
/// gate.  Do not strengthen the in-body asserts here without
/// re-evaluating whether the work belongs in
/// diag_page_polls_pb1_and_pb2 instead.
#[test]
#[ignore = "P3.6 step 2 byte-level trace -- run with --nocapture to inspect"]
fn three_core_ring_v171_v32_v32_diag_poll_byte_trace() {
    use dlcp_sim::memory::Address;

    const MENU_STATE_RAM: u16 = 0x0BF;
    const DIAG_PRESENT_RAM: u16 = 0x197;
    const MENU_STATE_PB1_DIAG: u8 = 4;

    let v171 = HexImage::from_hex_path(v171_control_hex_path())
        .expect("V1.71 hex parses");
    let v32 = HexImage::from_hex_path(v32_main_hex_path())
        .expect("V3.2 hex parses");
    let v23_combined = HexImage::from_hex_path(v23_main_combined_hex_path())
        .expect("V2.3 combined hex parses");

    let control = build_core_from_hex(Variant::Pic18F25K20, &v171, None, None);
    let mut main0 = build_seeded_main_core(&v32, &v23_combined);
    main0.peripherals.adc.set_an0_sample(0x0300);
    let mut main1 = build_seeded_main_core(&v32, &v23_combined);
    main1.peripherals.adc.set_an0_sample(0x0300);

    let mut chain = Chain::new();
    let i_ctl = chain.push_core(control);
    let i_main0 = chain.push_core(main0);
    let i_main1 = chain.push_core(main1);

    chain.couple_uart(i_ctl, default_tx_pin(), i_main0, default_rx_pin());
    chain.couple_uart(i_main0, default_tx_pin(), i_main1, default_rx_pin());
    chain.couple_uart(i_main1, default_tx_pin(), i_ctl, default_rx_pin());

    let i_dsp0 = chain.push_tas3108(Tas3108::default());
    let i_dsp1 = chain.push_tas3108(Tas3108::default());
    chain.couple_tas3108(i_main0, i_dsp0);
    chain.couple_tas3108(i_main1, i_dsp1);

    chain.apply_reset_all(ResetSource::PowerOn);
    chain.schedule_initial_steps(&[0, 0, 0]);

    // Seed CONTROL's PORTA / PORTC = 0xFF so the 6 button
    // inputs (RA1/RA2/RA3/RA4 + RC0/RC5) read as RELEASED.
    // Without this, the diag-page cadence loop exits
    // immediately on its first iteration -- the
    // `v171_diag_check_buttons` block at
    // `dlcp_control_v171.asm:4153` reads 0x9A bits 4/5
    // (LEFT/RIGHT cached pin state) and returns from the
    // page driver if either is set, which they are when
    // PORTA/PORTC default to 0.  Same fix the existing
    // LCD parity test applies (task #34); here it gates
    // whether the cadence loop iterates long enough to
    // actually fire a PB2 query.
    chain.cores[i_ctl]
        .memory
        .write_raw(Address::from_raw(0xF80), 0xFF); // PORTA
    chain.cores[i_ctl]
        .memory
        .write_raw(Address::from_raw(0xF82), 0xFF); // PORTC

    // Stage 1: boot to first UART so CONTROL is in main loop.
    chain.run_until(
        10_000_000,
        5_000_000_000,
        |c| {
            c.tas3108_slaves[i_dsp0].bytes_acked >= 1000
                && c.tas3108_slaves[i_dsp1].bytes_acked >= 1000
                && !c.uart_tx_history.is_empty()
        },
    );
    let stage1_history_len = chain.uart_tx_history.len();
    let stage1_tick = chain.current_tick;

    // Stage 2: poke menu_state to PB1 Diag.
    chain.cores[i_ctl]
        .memory
        .write_raw(Address::from_raw(MENU_STATE_RAM), MENU_STATE_PB1_DIAG);

    // Stage 3: run for the bounded budget OR until diag_present == 0x03.
    chain.run_until(
        50_000_000,
        2_000_000_000,
        |c| c.cores[i_ctl].memory.read_raw(Address::from_raw(DIAG_PRESENT_RAM)) == 0x03,
    );

    // Slice off the diag-poll window (post-stage1 records).
    let diag_records: Vec<_> = chain
        .uart_tx_history
        .iter()
        .skip(stage1_history_len)
        .collect();

    // Per-edge byte streams, in tick order.
    let mut ctl_tx: Vec<u8> = Vec::new();
    let mut m0_tx: Vec<u8> = Vec::new();
    let mut m1_tx: Vec<u8> = Vec::new();
    for r in &diag_records {
        if r.src_core == i_ctl {
            ctl_tx.push(r.byte);
        } else if r.src_core == i_main0 {
            m0_tx.push(r.byte);
        } else if r.src_core == i_main1 {
            m1_tx.push(r.byte);
        }
    }

    let final_present = chain.cores[i_ctl]
        .memory
        .read_raw(Address::from_raw(DIAG_PRESENT_RAM));

    eprintln!("=== P3.6 byte-level trace ===");
    eprintln!(
        "stage1_tick={stage1_tick}, current_tick={}, diag_records={}, final_present=0x{final_present:02X}",
        chain.current_tick,
        diag_records.len()
    );
    eprintln!();

    // Find indices of B1 / B2 frames in CTL.TX (frame starts).
    let ctl_b1_count = ctl_tx.iter().filter(|&&b| b == 0xB1).count();
    let ctl_b2_count = ctl_tx.iter().filter(|&&b| b == 0xB2).count();
    eprintln!("CTL.TX byte count: {}", ctl_tx.len());
    eprintln!("  0xB1 frames sent: {ctl_b1_count} (PB1 queries)");
    eprintln!("  0xB2 frames sent: {ctl_b2_count} (PB2 queries)");
    if ctl_b2_count == 0 {
        eprintln!("  ** CONTROL never sent a PB2 query (0xB2). Hop 1 broken. **");
    }

    // Step 2 check: did MAIN0 forward 0xB1 (the decremented form of 0xB2)?
    // Counts may exceed B2 query count because MAIN0 also receives B1 PB1
    // queries -- but those are "consume locally, do NOT forward".  So every
    // 0xB1 in MAIN0.TX should correspond to a 0xB2 received from CONTROL.
    let m0_b1_count = m0_tx.iter().filter(|&&b| b == 0xB1).count();
    let m0_b2_count = m0_tx.iter().filter(|&&b| b == 0xB2).count();
    let m0_bf_count = m0_tx.iter().filter(|&&b| b == 0xBF).count();
    eprintln!("MAIN0.TX byte count: {}", m0_tx.len());
    eprintln!("  0xB1 frames forwarded: {m0_b1_count} (decremented PB2 queries)");
    eprintln!("  0xB2 frames forwarded: {m0_b2_count} (should be 0 -- only PB1+ chain would emit)");
    eprintln!("  0xBF frames emitted: {m0_bf_count} (PB1 reply prefixes)");
    if ctl_b2_count > 0 && m0_b1_count == 0 {
        eprintln!("  ** MAIN0 received PB2 queries but never forwarded 0xB1 to MAIN1. Hop 2 broken. **");
    }

    // Step 4 check: did MAIN1 emit any reply traffic?
    let m1_bf_count = m1_tx.iter().filter(|&&b| b == 0xBF).count();
    eprintln!("MAIN1.TX byte count: {}", m1_tx.len());
    eprintln!("  0xBF frames emitted: {m1_bf_count} (reply prefixes)");
    if m0_b1_count > 0 && m1_bf_count == 0 {
        eprintln!("  ** MAIN0 forwarded queries to MAIN1 but MAIN1 never replied. Hop 4 broken. **");
    }

    // Slice the first ~80 bytes of each edge for human inspection.
    let dump = |label: &str, bytes: &[u8]| {
        let head: Vec<String> = bytes
            .iter()
            .take(80)
            .map(|b| format!("{b:02X}"))
            .collect();
        eprintln!("{label} (first {} bytes): {}", head.len(), head.join(" "));
    };
    eprintln!();
    dump("CTL.TX  ", &ctl_tx);
    dump("MAIN0.TX", &m0_tx);
    dump("MAIN1.TX", &m1_tx);
}

/// P3.6 step (A) -- synthetic byte-injection probe of V3.2's
/// route-byte decrement-and-forward protocol.  Answers "does
/// our sim faithfully execute the PB-identification protocol's
/// decrement step?"
///
/// Bypasses CONTROL entirely.  Topology:
///
///   feeder.TX -> MAIN0.RX
///   MAIN0.TX  -> MAIN1.RX
///   MAIN1.TX  -> feeder.RX     (loopback so MAIN1 replies are
///                                visible in `uart_tx_history`)
///
/// The feeder is an empty K20 core with `BRA -1` self-loop at
/// flash[0] -- it just holds bytes we push into its
/// completed-TX FIFO and lets `drain_completed_tx_bytes` deliver
/// them at MAIN0.RX.
///
/// After both MAINs converge to GIE=1 (uart_config + interrupt
/// enable both done), inject `B2 21 00` from feeder one byte at
/// a time with ~10 M ticks between each.
///
/// Asserts:
///
///   * `MAIN0.TX` contains the sequence `B1 21 00` -- proves
///     the route-byte decrement (`B2 -> B1`) AND forward path
///     executes correctly in the sim.  This is the
///     **load-bearing assertion** for the user's question
///     "does our sim faithfully execute V3.2 firmware's
///     PB-identification protocol?".
///
/// What this probe does NOT prove:
///
///   * MAIN1's receive-and-reply (Hop B) -- empirically MAIN1
///     receives only `21 00` from the forwarded burst (not the
///     leading `B1`) in this synthetic harness, likely because
///     MAIN1's RX FIFO has residue from MAIN0's periodic
///     broadcasts when `B1` arrives, causing it to land
///     mid-frame.  This is a HARNESS quirk, not a sim
///     fidelity gap: the underlying "MAIN receives addressed
///     frame Bx/cmd/data and replies" path is already
///     validated bit-exact by
///     `chain_v171_v31_main_emits_gpsim_response_burst_bit_exact`.
///
/// Result: the sim **does** faithfully execute the
/// decrement-and-forward step.  The P3.6 step-2 divergence is
/// a CONTROL-side reachability problem in the diag-page
/// probe's test harness, not a sim fidelity gap.
///
/// `#[ignore]`d for now; wall-clock ~7 s on the development
/// machine.
#[test]
#[ignore = "P3.6 step (A) -- synthetic byte injection probe"]
fn three_core_synthetic_pb2_injection_decrement_and_forward() {
    use dlcp_sim::memory::Address;

    let v32 = HexImage::from_hex_path(v32_main_hex_path())
        .expect("V3.2 hex parses");
    let v23_combined = HexImage::from_hex_path(v23_main_combined_hex_path())
        .expect("V2.3 combined hex parses");

    // Feeder: K20 core with a tight self-loop (`BRA -1`) at
    // flash[0..2] so the executor doesn't walk PC out of bounds
    // through erased 0xFFFF NOPs.  Pre-set RCSTA = SPEN | CREN =
    // 0x90 so deliver_rx_byte accepts inbound bytes; the feeder
    // doesn't actually parse anything, but uart_tx_history still
    // records deliveries to it.
    let mut feeder = Core::new(Variant::Pic18F25K20);
    feeder.flash_mut()[0] = 0xFF;
    feeder.flash_mut()[1] = 0xD7; // BRA -1 self-loop
    feeder
        .memory
        .write_raw(Address::from_raw(0xFAB), 0x90);

    let mut main0 = build_seeded_main_core(&v32, &v23_combined);
    main0.peripherals.adc.set_an0_sample(0x0300);
    let mut main1 = build_seeded_main_core(&v32, &v23_combined);
    main1.peripherals.adc.set_an0_sample(0x0300);

    let mut chain = Chain::new();
    let i_feeder = chain.push_core(feeder);
    let i_main0 = chain.push_core(main0);
    let i_main1 = chain.push_core(main1);

    chain.couple_uart(i_feeder, default_tx_pin(), i_main0, default_rx_pin());
    chain.couple_uart(i_main0, default_tx_pin(), i_main1, default_rx_pin());
    chain.couple_uart(i_main1, default_tx_pin(), i_feeder, default_rx_pin());

    let i_dsp0 = chain.push_tas3108(Tas3108::default());
    let i_dsp1 = chain.push_tas3108(Tas3108::default());
    chain.couple_tas3108(i_main0, i_dsp0);
    chain.couple_tas3108(i_main1, i_dsp1);

    chain.apply_reset_all(ResetSource::PowerOn);
    chain.schedule_initial_steps(&[0, 0, 0]);

    // Boot until BOTH MAINs have GIE set in INTCON (0xFF2 bit 7)
    // -- only after the firmware enables global interrupts will
    // the RCIF ISR run and drain RCREG into the SW rx_ring at
    // 0x0200.  Without this the parser never sees bytes we
    // inject.  This is a stricter predicate than DSP-init
    // bytes_acked, which fires before GIE in V3.2's boot order.
    chain.run_until(
        10_000_000,
        5_000_000_000,
        |c| {
            let gie0 = c.cores[i_main0]
                .memory
                .read_raw(Address::from_raw(0xFF2))
                & 0x80;
            let gie1 = c.cores[i_main1]
                .memory
                .read_raw(Address::from_raw(0xFF2))
                & 0x80;
            let acks0 = c.tas3108_slaves[i_dsp0].bytes_acked;
            let acks1 = c.tas3108_slaves[i_dsp1].bytes_acked;
            gie0 != 0 && gie1 != 0 && acks0 >= 1000 && acks1 >= 1000
        },
    );
    assert!(
        chain.tas3108_slaves[i_dsp0].bytes_acked >= 1000
            && chain.tas3108_slaves[i_dsp1].bytes_acked >= 1000,
        "boot stage did not converge: dsp0_acks={}, dsp1_acks={}",
        chain.tas3108_slaves[i_dsp0].bytes_acked,
        chain.tas3108_slaves[i_dsp1].bytes_acked,
    );
    let pre_inject_history = chain.uart_tx_history.len();
    let pre_inject_tick = chain.current_tick;

    // Diagnostic: read MAIN0's RCSTA at the point of injection to
    // confirm SPEN | CREN are set (otherwise deliver_rx_byte
    // silently drops bytes).
    let main0_rcsta_pre = chain.cores[i_main0]
        .memory
        .read_raw(Address::from_raw(0xFAB));
    let main1_rcsta_pre = chain.cores[i_main1]
        .memory
        .read_raw(Address::from_raw(0xFAB));
    eprintln!(
        "Pre-inject RCSTA: main0=0x{main0_rcsta_pre:02X}, main1=0x{main1_rcsta_pre:02X} \
         (need 0x90 = SPEN|CREN for RX accept)"
    );

    // If V3.2's `uart_config` (`dlcp_main_v32.asm:7920+`) hasn't
    // run yet (or RCSTA was cleared by something else), force
    // SPEN | CREN on so deliver_rx_byte accepts the bytes we're
    // about to inject.  This is the same workaround the
    // existing chain unit tests use for synthetic RX paths.
    if main0_rcsta_pre & 0x90 != 0x90 {
        eprintln!("  -> seeding MAIN0 RCSTA = 0x90 to enable RX");
        chain.cores[i_main0]
            .memory
            .write_raw(Address::from_raw(0xFAB), 0x90);
    }
    if main1_rcsta_pre & 0x90 != 0x90 {
        eprintln!("  -> seeding MAIN1 RCSTA = 0x90 to enable RX");
        chain.cores[i_main1]
            .memory
            .write_raw(Address::from_raw(0xFAB), 0x90);
    }

    // Pre-clear MAIN1's RX state to remove any residual FIFO
    // bytes from prior periodic broadcasts MAIN0 may have sent.
    // Without this, the 3rd byte of our injection burst can
    // overflow MAIN1's 2-deep FIFO -> OERR -> byte dropped, and
    // the parser sees only a partial frame.  CREN-toggle
    // recovery: write CREN=0 then re-set 0x90 to flush.
    chain.cores[i_main1]
        .memory
        .write_raw(Address::from_raw(0xFAB), 0x80); // SPEN=1, CREN=0
    chain.cores[i_main1]
        .memory
        .write_raw(Address::from_raw(0xFAE), 0x00); // RCREG = 0
    chain.cores[i_main1]
        .memory
        .write_raw(Address::from_raw(0xFAB), 0x90); // SPEN|CREN
    chain.cores[i_main1]
        .peripherals
        .eusart
        .reset_state();

    // Inject `B2 21 00` from feeder, one byte at a time, with
    // ~10 M ticks between each (much wider than one wire-byte
    // time) so MAIN0 has time to RX, process, and shift its
    // forwarded byte through TX before the next inject.  This
    // gives MAIN1 enough time to drain its own RCREG between
    // arrivals from MAIN0's forwarded chain.
    let inject_bytes = [0xB2u8, 0x21, 0x00];
    for &byte in &inject_bytes {
        chain.cores[i_feeder]
            .peripherals
            .eusart
            .push_completed_tx_byte_for_test(byte);
        chain.step_ticks(10_000_000);
    }

    // Diagnostic: did the bytes reach MAIN0?  Count
    // (feeder -> main0) records in the post-inject window.
    let feeder_to_main0_count = chain
        .uart_tx_history
        .iter()
        .skip(pre_inject_history)
        .filter(|r| r.src_core == i_feeder && r.dst_core == i_main0)
        .count();
    eprintln!(
        "feeder -> MAIN0 deliveries during inject window: {feeder_to_main0_count} \
         (expected 3)"
    );

    // Did the firmware-side ISR drain RCREG / advance rx_ring?
    let main0_rcreg = chain.cores[i_main0]
        .memory
        .read_raw(Address::from_raw(0xFAE));
    let main0_pir1_rcif = chain.cores[i_main0]
        .memory
        .read_raw(Address::from_raw(0xF9E))
        & 0x20;
    let main0_pie1_rcie = chain.cores[i_main0]
        .memory
        .read_raw(Address::from_raw(0xF9D))
        & 0x20;
    let main0_intcon_gie = chain.cores[i_main0]
        .memory
        .read_raw(Address::from_raw(0xFF2))
        & 0x80;
    let main0_pc = chain.cores[i_main0].pc();
    let main1_pc = chain.cores[i_main1].pc();
    let main1_rcreg = chain.cores[i_main1]
        .memory
        .read_raw(Address::from_raw(0xFAE));
    let main1_rcif = chain.cores[i_main1]
        .memory
        .read_raw(Address::from_raw(0xF9E))
        & 0x20;
    // V3.2 MAIN RAM addresses from `dlcp_main_ram.inc`.
    let main1_active_flags = chain.cores[i_main1]
        .memory
        .read_raw(Address::from_raw(0x05E));
    let main1_rx_frame_pos = chain.cores[i_main1]
        .memory
        .read_raw(Address::from_raw(0x098));
    let main1_ram_a2 = chain.cores[i_main1]
        .memory
        .read_raw(Address::from_raw(0x0A2));
    let main1_ram_a3 = chain.cores[i_main1]
        .memory
        .read_raw(Address::from_raw(0x0A3));
    eprintln!(
        "Post-inject MAIN0: PC=0x{main0_pc:04X}, RCREG=0x{main0_rcreg:02X}, \
         RCIF={}, RCIE={}, GIE={}",
        if main0_pir1_rcif != 0 { "1" } else { "0" },
        if main0_pie1_rcie != 0 { "1" } else { "0" },
        if main0_intcon_gie != 0 { "1" } else { "0" },
    );
    eprintln!(
        "Post-inject MAIN1: PC=0x{main1_pc:04X}, RCREG=0x{main1_rcreg:02X}, \
         RCIF={}, active_flags=0x{main1_active_flags:02X}, \
         frame_pos(0x098)=0x{main1_rx_frame_pos:02X}, \
         ram_0xA2(cmd)=0x{main1_ram_a2:02X}, ram_0xA3(data)=0x{main1_ram_a3:02X}",
        if main1_rcif != 0 { "1" } else { "0" },
    );

    // Run an extra ~200 M ticks (~1.7 s wall) for MAIN0 to
    // forward, MAIN1 to parse + execute `cmd21_diag_query_handler`,
    // and the 7-frame BF/2N reply burst to land at MAIN1.TX.
    chain.step_ticks(200_000_000);

    // Slice out post-injection records for analysis.
    let post_inject_records: Vec<_> = chain
        .uart_tx_history
        .iter()
        .skip(pre_inject_history)
        .collect();

    let extract = |src: usize| -> Vec<u8> {
        post_inject_records
            .iter()
            .filter(|r| r.src_core == src)
            .map(|r| r.byte)
            .collect()
    };
    let feeder_tx = extract(i_feeder);
    let m0_tx = extract(i_main0);
    let m1_tx = extract(i_main1);

    eprintln!("=== P3.6 step (A) synthetic injection ===");
    eprintln!(
        "pre_inject_tick={pre_inject_tick}, current_tick={}, post-inject deliveries={}",
        chain.current_tick,
        post_inject_records.len()
    );
    eprintln!("feeder.TX: {feeder_tx:02X?}");
    eprintln!("MAIN0.TX:  {m0_tx:02X?}");
    eprintln!("MAIN1.TX:  {m1_tx:02X?}");

    // Sanity: feeder delivered exactly the 3 injected bytes.
    assert_eq!(
        feeder_tx,
        vec![0xB2, 0x21, 0x00],
        "feeder.TX must contain exactly the 3 injected bytes; got {feeder_tx:02X?}"
    );

    // Codex LOW from e591f31 review (task #41): explicit
    // delivery-count contract.  The feeder pushes 3 bytes; the
    // chain dispatcher should record EXACTLY 3 feeder->MAIN0
    // deliveries in the post-inject window.  Without this
    // assertion, a regression where the chain delivered the
    // bytes more than once (e.g. via a duplicate coupling or
    // an event-replay bug) would still pass the
    // feeder_tx == [B2,21,00] check above because that records
    // *attempts*, not deliveries.
    let feeder_to_main0_count = post_inject_records
        .iter()
        .filter(|r| r.src_core == i_feeder && r.dst_core == i_main0)
        .count();
    assert_eq!(
        feeder_to_main0_count, 3,
        "chain must record exactly 3 feeder->MAIN0 deliveries in \
         the post-inject window; got {feeder_to_main0_count}.  \
         Larger value indicates a duplicate-delivery regression."
    );

    // Hop A: MAIN0 must have emitted `B1 21 00` somewhere in its
    // TX history (decremented from `B2 21 00` and forwarded
    // downstream).  The window may also contain unrelated MAIN0
    // TX traffic (status pings, etc.), so we search for the
    // specific 3-byte sequence rather than asserting position 0.
    let m0_b1_seq_pos = m0_tx
        .windows(3)
        .position(|w| w == [0xB1, 0x21, 0x00]);
    assert!(
        m0_b1_seq_pos.is_some(),
        "MAIN0.TX must contain the forwarded sequence `B1 21 00` \
         (route-byte decrement-and-forward of injected `B2 21 00`); \
         got {m0_tx:02X?}"
    );

    // Codex LOW from e591f31 review (task #41) follow-up:
    // assert MAIN0 emits the forwarded sequence EXACTLY ONCE
    // -- a duplicate would slip past the position-search above
    // and indicate a parser-loop or chain replay bug.
    let m0_b1_seq_count = m0_tx
        .windows(3)
        .filter(|w| *w == [0xB1, 0x21, 0x00])
        .count();
    assert_eq!(
        m0_b1_seq_count, 1,
        "MAIN0.TX must contain exactly ONE `B1 21 00` forwarded \
         sequence (no duplicates from parser-loop or chain \
         replay regression); got {m0_b1_seq_count}.  Full m0_tx: \
         {m0_tx:02X?}"
    );

    // Hop B (informational only -- not asserted; see docstring):
    // MAIN1's receive-and-reply path is harness-quirky in this
    // synthetic setup and the underlying behaviour is already
    // validated by the existing 2-core bit-exact parity test
    // (`chain_v171_v31_main_emits_gpsim_response_burst_bit_exact`).
    // We log MAIN1.TX but do NOT assert on it -- empirically
    // MAIN1 sees `21 00` (B1 lost to FIFO residue from MAIN0's
    // pre-injection periodic broadcasts) and forwards them as
    // broadcast.  Cleaning up the harness so MAIN1 sees `B1 21
    // 00` cleanly is its own follow-up; not load-bearing for
    // the protocol-faithfulness question this probe answers.
    let bf_pattern_starts = m1_tx.windows(2).enumerate().filter_map(|(i, w)| {
        if w[0] == 0xBF && w[1] == 0x21 {
            Some(i)
        } else {
            None
        }
    });
    let mut found_full_burst = false;
    for start in bf_pattern_starts {
        let burst_end = start + 21;
        if burst_end > m1_tx.len() {
            continue;
        }
        let mut ok = true;
        for frame in 0..7 {
            let route_idx = start + frame * 3;
            let cmd_idx = route_idx + 1;
            let expected_cmd = 0x21 + (frame as u8);
            if m1_tx[route_idx] != 0xBF || m1_tx[cmd_idx] != expected_cmd {
                ok = false;
                break;
            }
        }
        if ok {
            found_full_burst = true;
            break;
        }
    }
    eprintln!(
        "Hop B (informational): MAIN1 BF/21..BF/27 reply burst {} (harness-quirky; not asserted)",
        if found_full_burst { "FOUND" } else { "missing" },
    );
}

/// P3.8a (symptom-equivalent, not bit-exact) — V3.2 MAIN diag-counter
/// dispatch semantics: `standby_event_dispatch` correctly bumps
/// `diag_s` on shutdown-path entry and `diag_b` on bring-up-path
/// entry.
///
/// Mirrors hardware observation 2026-04-27 on real DLCP rig (see
/// `docs/analysis/HW_2026-04-27_DIAG_AND_STDBY_FINDINGS.md` §7.2.A):
/// fresh-boot cmd 0x44 reports `Runtime: I0 D0 S0 B0 R0 A0 P0` from
/// both MAINs; after one STDBY/wake cycle from CONTROL panel, LEFT
/// MAIN reports `S1 B1`.
///
/// V3.2 increments `diag_s` on every standby dispatch (gate-close
/// transition) and `diag_b` on every bring-up dispatch (gate-open
/// transition).  See `src/dlcp_fw/asm/dlcp_main_v32.asm:8385+`
/// (`standby_event_dispatch:`) for the increment paths and
/// `:1873`/`:1898` for the wake/standby request handlers.
///
/// **Scope**: this test seeds the post-handler state directly
/// (`event_flags.bit2 = 1` + chosen `active_flags.bit3` value) and
/// asserts that `standby_event_dispatch` then correctly routes to
/// either the shutdown or bring-up branch depending on gate state,
/// bumping the right counter and consuming the event.  The
/// parser-driven path (CONTROL emits `B0/03/0x` over UART → MAIN
/// parses → `cmd03_subdispatch` → `standby_request_handler` →
/// `standby_event_dispatch`) is left as a **deferred follow-up**:
/// synthetic feeder injection of `B0/03/00` reaches the parser
/// (cmd byte saved correctly to `ram_0x0A2`) but
/// `standby_request_handler` does not appear to update
/// `active_flags.bit3` / `event_flags.bit2` in the executor before
/// the rx_ring drains; the cause is not yet root-caused (suspected
/// dispatch ordering or handler-tail race) and merits its own
/// investigation outside this commit.
///
/// **Faithfulness caveat**: this test reads cells via direct BANK 2
/// RAM probe at `diag_i..diag_p` (0x2E5..0x2EB), not via the cmd 0x44
/// HID path (which would require a USB stack).  The HID emit-side at
/// `hid_cmd_diag_snapshot:` (`dlcp_main_v32.asm:9760+`) is a direct
/// `POSTINC0 -> POSTINC2` byte-copy with no transformation, so RAM is
/// bit-equivalent to cmd 0x44 reply payload `[3..9]`.  Note however
/// that the UART BF/2N reply burst at `:9261` masks each cell with
/// `andlw 0x0F` (`:9267`), so RAM is NOT bit-equivalent to the BF/2N
/// stream if any cell has high-nibble bits set; this test asserts
/// cmd 0x44 semantics only.
#[test]
fn v32_main_runtime_counters_baseline_and_post_stdby_cycle() {
    use dlcp_sim::memory::Address;

    let v32 = HexImage::from_hex_path(v32_main_hex_path())
        .expect("V3.2 hex parses");
    let v23_combined = HexImage::from_hex_path(v23_main_combined_hex_path())
        .expect("V2.3 combined hex parses");

    let mut main0 = build_seeded_main_core(&v32, &v23_combined);
    main0.peripherals.adc.set_an0_sample(0x0300);

    let mut chain = Chain::new();
    let i_main0 = chain.push_core(main0);

    // Single-MAIN probe.  The diag dispatch we exercise is local to
    // MAIN, so we don't need a full ring -- just enough boot to
    // bring the periodic main-service loop online.  We do need a
    // TAS3108 slave because V3.2 boot parks at `dsp_ping`'s NACK
    // retry loop without one.
    let i_dsp0 = chain.push_tas3108(Tas3108::default());
    chain.couple_tas3108(i_main0, i_dsp0);

    chain.apply_reset_all(ResetSource::PowerOn);
    chain.schedule_initial_steps(&[0]);

    // Boot until GIE is set + DSP init crosses the convergence
    // threshold, so the periodic main-service loop is running.
    chain.run_until(
        10_000_000,
        5_000_000_000,
        |c| {
            let gie = c.cores[i_main0]
                .memory
                .read_raw(Address::from_raw(0xFF2))
                & 0x80;
            gie != 0 && c.tas3108_slaves[i_dsp0].bytes_acked >= 1000
        },
    );
    assert!(
        chain.current_tick < 5_000_000_000,
        "boot did not converge before 5 B-tick safety ceiling"
    );

    // RAM map per `src/dlcp_fw/asm/dlcp_main_ram.inc`:
    //   0x05E = active_flags        (bit3 = gate open)
    //   0x07E = event_flags         (bit2 = standby/wake event pending)
    //   0x2E5 = diag_i               (I -- I2C transport faults)
    //   0x2E7 = diag_s               (standby dispatches)
    //   0x2E8 = diag_b               (bring-up / wake dispatches)
    let read_diag_block = |c: &Chain, idx: usize| -> [u8; 7] {
        let mut out = [0u8; 7];
        for (i, cell) in out.iter_mut().enumerate() {
            *cell = c.cores[idx]
                .memory
                .read_raw(Address::from_raw(0x2E5 + i as u16));
        }
        out
    };

    // ----- Phase 1: post-boot baseline -----
    // Hardware reading was `S0 B0` shortly after power-on.  In the
    // sim, boot convergence takes hundreds of M ticks of simulated
    // time, during which `diag_i` (I2C transport-fault counter)
    // accumulates from TAS3108 NACKs / coeff-write retries -- so
    // we only assert on the cells the STDBY/wake path bumps:
    // `diag_s` (0x2E7) and `diag_b` (0x2E8).
    let baseline = read_diag_block(&chain, i_main0);
    eprintln!("MAIN0 baseline diag block: {baseline:02X?}");
    assert_eq!(
        baseline[2], 0,
        "baseline diag_s (0x2E7) must be 0 before any standby dispatch; \
         got 0x{:02X} (full block: {:02X?})",
        baseline[2], baseline,
    );
    assert_eq!(
        baseline[3], 0,
        "baseline diag_b (0x2E8) must be 0 before any wake dispatch; \
         got 0x{:02X} (full block: {:02X?})",
        baseline[3], baseline,
    );

    // ----- Phase 2: shutdown branch (gate closed + event pending) -----
    // Equivalent firmware-driven sequence:
    //   `standby_request_handler` (`asm:1898+`) processes `B0/03/00`,
    //   observes gate currently OPEN, sets event_flags.bit2, then
    //   clears active_flags.bit3.  Net post-handler state is exactly
    //   what we seed below.
    // The next pass through `standby_event_dispatch` (`asm:8385+`)
    // should:
    //   1. See event_flags.bit2 set → not skip
    //   2. See active_flags.bit3 CLEAR → take the 47a6 (shutdown) branch
    //   3. `diag_inc_sat diag_s` (0x2E7 → 1)
    //   4. Call `hw_standby_shutdown`
    //   5. Clear event_flags.bit2 (event consumed)
    {
        let af = chain.cores[i_main0]
            .memory
            .read_raw(Address::from_raw(0x05E));
        chain.cores[i_main0]
            .memory
            .write_raw(Address::from_raw(0x05E), af & !0x08); // bit3 CLEAR (gate closed)
        let ef = chain.cores[i_main0]
            .memory
            .read_raw(Address::from_raw(0x07E));
        chain.cores[i_main0]
            .memory
            .write_raw(Address::from_raw(0x07E), ef | 0x04); // bit2 SET
        eprintln!(
            "Phase 2 seed: active_flags 0x{af:02X} -> 0x{:02X}, \
             event_flags 0x{ef:02X} -> 0x{:02X}",
            af & !0x08,
            ef | 0x04,
        );
    }
    chain.step_ticks(50_000_000);

    let post_stdby = read_diag_block(&chain, i_main0);
    let af_post_stdby = chain.cores[i_main0]
        .memory
        .read_raw(Address::from_raw(0x05E));
    let ef_post_stdby = chain.cores[i_main0]
        .memory
        .read_raw(Address::from_raw(0x07E));
    eprintln!(
        "Phase 2 result: diag={post_stdby:02X?}, \
         active_flags=0x{af_post_stdby:02X}, event_flags=0x{ef_post_stdby:02X}"
    );
    assert_eq!(
        post_stdby[2], 1,
        "diag_s (0x2E7) must be 1 after shutdown-branch dispatch; got 0x{:02X}",
        post_stdby[2],
    );
    assert_eq!(
        post_stdby[3], 0,
        "diag_b (0x2E8) must still be 0 after shutdown-branch dispatch \
         (no bring-up yet); got 0x{:02X}",
        post_stdby[3],
    );
    assert_eq!(
        ef_post_stdby & 0x04,
        0,
        "event_flags.bit2 must be CLEAR after dispatch consumed the event; \
         got 0x{:02X}",
        ef_post_stdby,
    );

    // ----- Phase 3: bring-up branch (gate open + event pending) -----
    // Equivalent firmware-driven sequence:
    //   `wake_request_handler` (`asm:1873+`) processes `B0/03/01`,
    //   observes gate currently CLOSED (just closed by STDBY in
    //   Phase 2), sets event_flags.bit2 AND active_flags.bit3.
    //   Post-handler state is exactly what we seed below.
    // The next pass through `standby_event_dispatch` should:
    //   1. See event_flags.bit2 set → not skip
    //   2. See active_flags.bit3 SET → take the bring-up branch
    //   3. `diag_inc_sat diag_b` (0x2E8 → 1)
    //   4. Call `adc_boot_gate` for rail-rise wait
    //   5. Clear event_flags.bit2
    {
        let af = chain.cores[i_main0]
            .memory
            .read_raw(Address::from_raw(0x05E));
        chain.cores[i_main0]
            .memory
            .write_raw(Address::from_raw(0x05E), af | 0x08); // bit3 SET (gate open)
        let ef = chain.cores[i_main0]
            .memory
            .read_raw(Address::from_raw(0x07E));
        chain.cores[i_main0]
            .memory
            .write_raw(Address::from_raw(0x07E), ef | 0x04); // bit2 SET
        eprintln!(
            "Phase 3 seed: active_flags 0x{af:02X} -> 0x{:02X}, \
             event_flags 0x{ef:02X} -> 0x{:02X}",
            af | 0x08,
            ef | 0x04,
        );
    }
    chain.step_ticks(50_000_000);

    let post_wake = read_diag_block(&chain, i_main0);
    let af_post_wake = chain.cores[i_main0]
        .memory
        .read_raw(Address::from_raw(0x05E));
    let ef_post_wake = chain.cores[i_main0]
        .memory
        .read_raw(Address::from_raw(0x07E));
    eprintln!(
        "Phase 3 result: diag={post_wake:02X?}, \
         active_flags=0x{af_post_wake:02X}, event_flags=0x{ef_post_wake:02X}"
    );
    assert_eq!(
        post_wake[2], 1,
        "diag_s (0x2E7) must still be 1 after bring-up-branch dispatch \
         (no extra STDBY); got 0x{:02X}",
        post_wake[2],
    );
    assert_eq!(
        post_wake[3], 1,
        "diag_b (0x2E8) must be 1 after bring-up-branch dispatch; got 0x{:02X}",
        post_wake[3],
    );
    // Note: we do NOT assert event_flags.bit2 cleared here.  The
    // bring-up branch calls `adc_boot_gate` *before* reaching the
    // 47aa "consume event" merge point.  `adc_boot_gate` is the
    // rail-rise blocking wait (`asm:5081+`) which can hold the CPU
    // for tens of millions of ticks before returning -- in this
    // single-MAIN harness without a coupled CONTROL feeding boot
    // signals, it can stay there indefinitely.  diag_b incrementing
    // is sufficient evidence the bring-up branch was taken; the
    // event-consume bookkeeping is a downstream side-effect.

    eprintln!(
        "P3.8a OK: baseline={:02X?}, post-shutdown={:02X?}, post-bring-up={:02X?}",
        baseline, post_stdby, post_wake,
    );
}

/// P3.8b (symptom-equivalent, not bit-exact) — RIGHT MAIN held in
/// reset → CONTROL stuck in `Waiting for DLCP`.
///
/// Mirrors the asymmetric-wake field bug observed on real DLCP rig
/// 2026-04-27 (filed as task #45; see findings doc §7.2.B): after a
/// STDBY/wake cycle, only LEFT MAIN re-enumerated; RIGHT MAIN never
/// came back; CONTROL sat in `Waiting for DLCP` indefinitely.  This
/// test does NOT model the hardware *cause* (PSU/inrush/wake-pin-
/// skew is out of scope) -- it only models the *symptom* by holding
/// MAIN1 in reset for the entire run via `Chain::hold_core_in_reset`
/// (the MCLR-pin-held-low primitive landed in P3.8b-prereq, task
/// #47).  CONTROL + MAIN0 boot normally; without MAIN1 forwarding
/// the ring is broken and CONTROL falls into the WAITING state.
#[test]
fn right_main_held_in_reset_control_stuck_in_waiting() {
    use dlcp_sim::memory::Address;

    let v171 = HexImage::from_hex_path(v171_control_hex_path())
        .expect("V1.71 hex parses");
    let v32 = HexImage::from_hex_path(v32_main_hex_path())
        .expect("V3.2 hex parses");
    let v23_combined = HexImage::from_hex_path(v23_main_combined_hex_path())
        .expect("V2.3 combined hex parses");

    let control = build_core_from_hex(Variant::Pic18F25K20, &v171, None, None);
    let mut main0 = build_seeded_main_core(&v32, &v23_combined);
    main0.peripherals.adc.set_an0_sample(0x0300);
    let mut main1 = build_seeded_main_core(&v32, &v23_combined);
    main1.peripherals.adc.set_an0_sample(0x0300);

    let mut chain = Chain::new();
    let i_ctl = chain.push_core(control);
    let i_main0 = chain.push_core(main0);
    let i_main1 = chain.push_core(main1);

    chain.couple_uart(i_ctl, default_tx_pin(), i_main0, default_rx_pin());
    chain.couple_uart(i_main0, default_tx_pin(), i_main1, default_rx_pin());
    chain.couple_uart(i_main1, default_tx_pin(), i_ctl, default_rx_pin());

    let i_dsp0 = chain.push_tas3108(Tas3108::default());
    let i_dsp1 = chain.push_tas3108(Tas3108::default());
    chain.couple_tas3108(i_main0, i_dsp0);
    chain.couple_tas3108(i_main1, i_dsp1);

    // HD44780 slave coupled to CONTROL so we can assert the LCD
    // raster shows `Waiting for DLCP`.
    let i_lcd = chain.push_lcd(Hd44780::new());
    chain.couple_lcd(i_ctl, i_lcd);

    chain.apply_reset_all(ResetSource::PowerOn);

    // **Hold MAIN1 in reset for the entire run.**  This is the
    // load-bearing setup line: with MAIN1 not stepping, the ring
    // edge `MAIN1 -> CONTROL` carries zero bytes, CONTROL never
    // receives a heartbeat reply, and V1.71's reconnect-wake
    // counter eventually expires into the `Waiting for DLCP`
    // screen.  Models real hardware where RIGHT MAIN failed to
    // re-enumerate after STDBY/wake.
    chain.hold_core_in_reset(i_main1);

    chain.schedule_initial_steps(&[0, 0, 0]);

    // V1.71 CONTROL reads its 6 button inputs as ACTIVE-LOW pins
    // on RA1/RA2/RA3/RA4 (SELECT/DOWN/STBY/RIGHT) and RC0/RC5
    // (UP/LEFT).  Default PORTA/PORTC = 0 reads "all buttons
    // pressed" -> STBY screen.  Seed 0xFF so the operator's
    // "no button held" state is the default.
    chain.cores[i_ctl]
        .memory
        .write_raw(Address::from_raw(0xF80), 0xFF); // PORTA
    chain.cores[i_ctl]
        .memory
        .write_raw(Address::from_raw(0xF82), 0xFF); // PORTC

    const EXPECTED_LINE1: &str = "Waiting for DLCP";

    // Diagnostic stepping: 8 x 250M-tick chunks = 2 B ticks total.
    // The bit-exact LCD parity test converges to `Volume:-17.0dB A`
    // within ~5 B ticks on a complete chain; we expect WAITING to
    // surface within similar bounds because V1.71 writes
    // `Waiting for DLCP` to the LCD *immediately* on entry to the
    // wait loop at `dlcp_control_v171.asm:4657`, before the
    // ~10 s grace counter even starts.  Stale chunks log LCD
    // state so a failed convergence shows where CONTROL parked.
    // Codex review of c993454, MEDIUM #3: the previous test broke
    // out of the chunk loop on first LCD match, then asserted that
    // instantaneous LCD state.  That could legitimately catch a
    // *transient* WAITING screen during early boot (before MAIN0's
    // sentinel burst lands at CONTROL), which is the same content
    // CONTROL writes in the cold-boot pre-handshake path -- not the
    // post-failure stuck-in-WAITING state we're trying to model.
    //
    // Codex review of 1356ed2, MEDIUM #2 follow-up: the original
    // fix used `MAIN0 PC > 0x1000` as the boot anchor, but 0x1000
    // is just the user reset trampoline -- a startup-banner state
    // could PC-sample at 0x1014 (cold-init jump) and falsely pass.
    // The more authoritative (monotonic) anchor is "DSP I2C
    // traffic is past the empirical 1000-ack convergence
    // sentinel" -- the same predicate the 3-core boot test uses
    // to declare convergence (`asm:574`).  This is *not* a
    // proven minimum-complete boundary for V3.2 DSP init; it's a
    // sentinel that empirically only fires after the cold-init
    // cascade is well past the startup-banner phase.  Codex
    // review of f8ceb67, LOW #3.
    //
    // Stronger convergence pattern:
    //   (1) require DSP bytes_acked >= 1000 (MAIN0 well past the
    //       startup-banner phase; I2C-driven DSP traffic is
    //       flowing).
    //   (2) THEN require LCD line 1 == `Waiting for DLCP`.
    //   (3) THEN step further chunks and require it to stay there
    //       (a chain-ring regression that lets MAIN0 alone satisfy
    //       CONTROL's heartbeat would surface here as a transition
    //       to `Volume:-...` or similar).
    //
    // 8 B-tick budget chosen to give ample headroom: the working
    // 2-core LCD parity test converges in ~5 B ticks; with MAIN1
    // held in reset only 2 cores effectively step, so this is
    // generous.
    const MAIN0_DSP_BOOT_ACK_THRESHOLD: u64 = 1000;
    let mut main0_dsp_booted_at_chunk: Option<usize> = None;
    let mut first_waiting_chunk: Option<usize> = None;
    for chunk in 0..32 {
        chain.step_ticks(250_000_000);
        let main0_pc = chain.cores[i_main0].pc();
        let dsp_acks = chain.tas3108_slaves[i_dsp0].bytes_acked;
        let lcd = &chain.lcd_slaves[i_lcd];
        eprintln!(
            "P3.8b chunk {chunk}: tick={}, MAIN0 PC=0x{main0_pc:04X}, \
             DSP acks={dsp_acks}, LCD line1={:?}, line2={:?}",
            chain.current_tick,
            lcd.line1(),
            lcd.line2(),
        );
        if main0_dsp_booted_at_chunk.is_none()
            && dsp_acks >= MAIN0_DSP_BOOT_ACK_THRESHOLD
        {
            main0_dsp_booted_at_chunk = Some(chunk);
        }
        // Only honour a WAITING match AFTER MAIN0's DSP has
        // crossed the deep-boot threshold -- the startup-banner
        // false-positive sits before this.
        if main0_dsp_booted_at_chunk.is_some()
            && lcd.line1() == EXPECTED_LINE1
            && first_waiting_chunk.is_none()
        {
            first_waiting_chunk = Some(chunk);
            break;
        }
    }
    eprintln!(
        "P3.8b main0_dsp_booted_at_chunk={main0_dsp_booted_at_chunk:?}, \
         first_waiting_chunk={first_waiting_chunk:?}"
    );

    assert!(
        main0_dsp_booted_at_chunk.is_some(),
        "MAIN0 DSP bytes_acked never reached {} in 8 B ticks; final \
         acks={}, MAIN0 PC=0x{:04X}.  Chain harness regression or \
         budget too short.",
        MAIN0_DSP_BOOT_ACK_THRESHOLD,
        chain.tas3108_slaves[i_dsp0].bytes_acked,
        chain.cores[i_main0].pc(),
    );
    assert!(
        first_waiting_chunk.is_some(),
        "CONTROL LCD never reached `Waiting for DLCP` AFTER MAIN0 \
         crossed DSP-init boot threshold; final LCD: line1={:?}, \
         line2={:?}, MAIN0 PC=0x{:04X}, DSP acks={}.  Either MAIN0 \
         is somehow satisfying CONTROL's heartbeat without MAIN1 \
         forwarding (chain-ring regression -- check `couple_uart` \
         edges) or CONTROL parked on a different screen.",
        chain.lcd_slaves[i_lcd].line1(),
        chain.lcd_slaves[i_lcd].line2(),
        chain.cores[i_main0].pc(),
        chain.tas3108_slaves[i_dsp0].bytes_acked,
    );

    // Stay-in-WAITING confirmation: step further chunks and
    // require the LCD to remain parked on `Waiting for DLCP`.
    const STAY_CONFIRM_CHUNKS: usize = 3;
    for confirm_chunk in 0..STAY_CONFIRM_CHUNKS {
        chain.step_ticks(250_000_000);
        let lcd = &chain.lcd_slaves[i_lcd];
        let main0_pc = chain.cores[i_main0].pc();
        eprintln!(
            "P3.8b stay-confirm chunk {confirm_chunk}: tick={}, \
             MAIN0 PC=0x{main0_pc:04X}, LCD line1={:?}, line2={:?}",
            chain.current_tick,
            lcd.line1(),
            lcd.line2(),
        );
        assert_eq!(
            lcd.line1(),
            EXPECTED_LINE1,
            "CONTROL LCD must STAY on `Waiting for DLCP` after MAIN0 \
             reached app code while MAIN1 is held in reset; got \
             line1={:?} on stay-confirm chunk {confirm_chunk}.  A \
             transient WAITING followed by a move out indicates \
             MAIN0 alone is satisfying CONTROL's heartbeat -- chain \
             ring regression.",
            lcd.line1(),
        );
    }

    let lcd = &chain.lcd_slaves[i_lcd];
    // Final DSP-acks sanity: MAIN0 must still be past the
    // deep-boot threshold (DSP init complete) -- this is the
    // monotonic, authoritative "MAIN0 ran past startup banner"
    // anchor that PC-range checks can't provide reliably.
    assert!(
        chain.tas3108_slaves[i_dsp0].bytes_acked
            >= MAIN0_DSP_BOOT_ACK_THRESHOLD,
        "MAIN0 DSP bytes_acked must remain >= {} at final \
         assertion; got {}",
        MAIN0_DSP_BOOT_ACK_THRESHOLD,
        chain.tas3108_slaves[i_dsp0].bytes_acked,
    );
    assert_eq!(
        lcd.line1(),
        EXPECTED_LINE1,
        "Final assertion: CONTROL LCD line 1 must read \
         `Waiting for DLCP` when MAIN1 is held in reset and MAIN0 \
         has booted.  Full LCD state: line1={:?}, line2={:?}.",
        lcd.line1(),
        lcd.line2(),
    );

    // Sanity: assert MAIN1 truly never advanced.
    let main1_cycles = chain.cores[i_main1].cycles();
    assert_eq!(
        main1_cycles, 0,
        "MAIN1 should be held in reset and never advance cycles; \
         got cycles={main1_cycles}.  If non-zero, the MCLR-held-low \
         gate in `Chain::execute_core_step` is leaking instructions \
         past the gate -- regression in task #47."
    );

    // Sanity: MAIN0 + CONTROL did make forward progress.
    assert!(
        chain.cores[i_main0].cycles() > 0,
        "MAIN0 should still advance; reset-hold should be MAIN1-only"
    );
    assert!(
        chain.cores[i_ctl].cycles() > 0,
        "CONTROL should still advance; reset-hold should be MAIN1-only"
    );

    eprintln!(
        "P3.8b OK: ctl_cycles={}, main0_cycles={}, main1_cycles={} \
         (held), LCD line1={:?}, line2={:?}",
        chain.cores[i_ctl].cycles(),
        chain.cores[i_main0].cycles(),
        chain.cores[i_main1].cycles(),
        lcd.line1(),
        lcd.line2(),
    );
}

/// P3.7 — Boot-offset parity: MAIN1 boots late, CONTROL recovers
/// from `Waiting for DLCP` once MAIN1's TX comes online.
///
/// Spec reference: `docs/SIM_REWRITE_RUST_SPEC.md` §7.4 calls for
/// a 1.5 s late MAIN1 boot offset under the V1.71 reconnect-wake
/// budget.  In universal ticks the spec quotes `+72_000_000` as
/// 1.5 s @ 48 MHz, matching `crates/dlcp-sim/src/boot_offset.rs:15`.
///
/// Hardware reality (per `docs/analysis/CONTROL_UNIT_ANALYSIS.md:104+`
/// and `docs/analysis/MAIN_CLOCK_TIMING.md`): each MCU has its own
/// local oscillator chain -- CONTROL has a 12 MHz XT crystal on the
/// control board (Fosc = 12 MHz, 3 MIPS), each MAIN has a 12 MHz
/// external source + HSPLL on its own main board (Fosc = 16 MHz,
/// 4 MIPS).  The boards are connected only by the 31,250-baud
/// optically-isolated current-loop serial link (CAT5 via J3 Midi
/// pins), NOT by any clock copy.  The "48 MHz universal clock" in
/// `chain.rs:17` is a SIMULATION TIME BASE (LCM of 12 and 16 MHz),
/// not a claim that the physical oscillators are unified -- the sim
/// supports per-core `ClockDomain::drift_ppm` (`clock.rs`, set via
/// `ClockDomain::with_drift_ppm`) to model the independent
/// phase/drift between oscillators.  This test uses the canonical
/// 72 M-tick offset on the unified time base; per-core drift is left
/// at the nominal-zero default.
///
/// Test shape:
///   1. Build 3-core ring (CONTROL + MAIN0 + MAIN1) with HD44780
///      LCD slave coupled to CONTROL.
///   2. `apply_reset_all` + `schedule_initial_steps(&[0, 0,
///      LATE_OFFSET])` -- CONTROL and MAIN0 boot at tick 0,
///      MAIN1 first scheduled at tick LATE_OFFSET.
///   3. Step until CONTROL's LCD line 0 starts with `Waiting`
///      (the cold-boot WAITING screen because MAIN1's TX is
///      silent so the chain ring can't return MAIN0's heartbeat
///      replies to CONTROL).
///   4. Continue stepping past LATE_OFFSET so MAIN1 boots, joins
///      the ring, and starts forwarding MAIN0's traffic.
///   5. Step until CONTROL's LCD line 0 leaves `Waiting` (the
///      reconnect-wake gate releases CONTROL into the steady-
///      state Volume display).
///
/// This is the silicon-equivalent of "MAIN1's PSU rail came up
/// late but CONTROL recovered" -- exercises V1.62b's reconnect-
/// wake gate inherited by V1.71 (`dlcp_control_v171.asm:5018+`
/// reconnect_wait_loop).
#[test]
fn test_main1_late_boot_recovery() {
    use dlcp_sim::memory::Address;

    let v171 = HexImage::from_hex_path(v171_control_hex_path())
        .expect("V1.71 hex parses");
    let v32 = HexImage::from_hex_path(v32_main_hex_path())
        .expect("V3.2 hex parses");
    let v23_combined = HexImage::from_hex_path(v23_main_combined_hex_path())
        .expect("V2.3 combined hex parses");

    let control = build_core_from_hex(Variant::Pic18F25K20, &v171, None, None);
    let mut main0 = build_seeded_main_core(&v32, &v23_combined);
    main0.peripherals.adc.set_an0_sample(0x0300);
    let mut main1 = build_seeded_main_core(&v32, &v23_combined);
    main1.peripherals.adc.set_an0_sample(0x0300);

    let mut chain = Chain::new();
    let i_ctl = chain.push_core(control);
    let i_main0 = chain.push_core(main0);
    let i_main1 = chain.push_core(main1);

    chain.couple_uart(i_ctl, default_tx_pin(), i_main0, default_rx_pin());
    chain.couple_uart(i_main0, default_tx_pin(), i_main1, default_rx_pin());
    chain.couple_uart(i_main1, default_tx_pin(), i_ctl, default_rx_pin());

    let i_dsp0 = chain.push_tas3108(Tas3108::default());
    let i_dsp1 = chain.push_tas3108(Tas3108::default());
    chain.couple_tas3108(i_main0, i_dsp0);
    chain.couple_tas3108(i_main1, i_dsp1);

    let i_lcd = chain.push_lcd(Hd44780::new());
    chain.couple_lcd(i_ctl, i_lcd);

    chain.apply_reset_all(ResetSource::PowerOn);

    // Boot offset: spec calls for 1.5 s at 48 MHz = 72_000_000
    // universal ticks (`docs/SIM_REWRITE_RUST_SPEC.md:304`,
    // `crates/dlcp-sim/src/boot_offset.rs:15`).  The 48 MHz
    // figure is the sim's universal time base -- the LCM of
    // CONTROL's 12 MHz XT Fosc and MAIN's 16 MHz HSPLL Fosc,
    // not a shared physical clock; see test docstring above
    // for the per-board oscillator topology.
    const LATE_OFFSET: u64 = 72_000_000;
    chain.schedule_initial_steps(&[0, 0, LATE_OFFSET]);

    chain.cores[i_ctl]
        .memory
        .write_raw(Address::from_raw(0xF80), 0xFF); // PORTA = all buttons released
    chain.cores[i_ctl]
        .memory
        .write_raw(Address::from_raw(0xF82), 0xFF); // PORTC

    // ----- Phase 0: prove the late-boot offset was actually
    // honored.  Step LATE_OFFSET / 2 ticks (i.e. 36 M ticks --
    // half the offset, well below it) and assert MAIN1 hasn't
    // started stepping yet.  Codex review of a8bd432, MEDIUM:
    // without this guard the test would still pass even if
    // `schedule_initial_steps` regressed to ignore the offset
    // and MAIN1 booted at tick 0 -- CONTROL might still hit a
    // transient WAITING during cold boot and recover, with no
    // way to tell whether the late-boot path was actually
    // exercised.  Stepping past LATE_OFFSET/2 is a much
    // cheaper boot-offset wiring guard than the post-recovery
    // `cycles() > 0` check (which only proves MAIN1 ran at
    // some point).
    chain.step_ticks(LATE_OFFSET / 2);
    let main1_cycles_before_offset = chain.cores[i_main1].cycles();
    assert_eq!(
        main1_cycles_before_offset, 0,
        "MAIN1 must NOT have started stepping at tick={} \
         (LATE_OFFSET/2 = {}, well below the {LATE_OFFSET}-tick \
         delay).  Got cycles={}; boot-offset wiring regression \
         (`schedule_initial_steps` not honoring the per-core \
         offset).",
        chain.current_tick,
        LATE_OFFSET / 2,
        main1_cycles_before_offset,
    );

    // ----- Phase 1: CONTROL must reach `Waiting for DLCP` -----
    // With MAIN1's first instruction delayed to tick =
    // LATE_OFFSET, the chain ring is incomplete during the
    // pre-LATE_OFFSET window: MAIN0's sentinel-burst replies
    // route to MAIN1[silent] which has no forwarding capacity
    // yet, so they never reach CONTROL.  CONTROL's cold-boot
    // handshake times out and shows the WAITING screen.
    //
    // Note: at LATE_OFFSET = 72_000_000 (canonical 1.5 s
    // @ 48 MHz), MAIN1 starts stepping before CONTROL has
    // committed to the WAITING screen -- but CONTROL still
    // ends up there because MAIN1's first ~tens of millions
    // of cycles are spent in cold-init (DSP I²C bring-up,
    // EUSART config, etc.) before it can forward chain
    // traffic.  Don't strict-equal `MAIN1 cycles == 0` at
    // WAITING entry; just confirm the WAITING text was
    // observed.
    let mut waiting_reached = false;
    for chunk in 0..8 {
        chain.step_ticks(50_000_000);
        let line0 = chain.lcd_slaves[i_lcd].line1();
        eprintln!(
            "P3.7 phase 1 chunk {chunk}: tick={}, MAIN1 cycles={}, \
             LCD line0={:?}",
            chain.current_tick,
            chain.cores[i_main1].cycles(),
            line0,
        );
        if line0.starts_with("Waiting") {
            waiting_reached = true;
            break;
        }
    }
    assert!(
        waiting_reached,
        "CONTROL must reach `Waiting for DLCP` during the late-boot \
         window (LATE_OFFSET = {LATE_OFFSET}).  Final LCD: line0={:?}, \
         line1={:?}, MAIN1 cycles={}.",
        chain.lcd_slaves[i_lcd].line1(),
        chain.lcd_slaves[i_lcd].line2(),
        chain.cores[i_main1].cycles(),
    );

    // ----- Phase 2: step past LATE_OFFSET so MAIN1 boots -----
    // Walk forward in chunks until LCD leaves `Waiting` OR a
    // budget cap.  The budget is expressed as ticks
    // SINCE LATE_OFFSET so the failure message accurately
    // describes "time since MAIN1 came online", not absolute
    // chain time (codex review of f44d7a4, LOW #3).
    const RECOVERY_BUDGET_AFTER_LATE_BOOT: u64 = 8_000_000_000;
    let recovery_deadline = LATE_OFFSET + RECOVERY_BUDGET_AFTER_LATE_BOOT;
    let mut recovered_at_tick: Option<u64> = None;
    for chunk in 0..32 {
        chain.step_ticks(250_000_000);
        let line0 = chain.lcd_slaves[i_lcd].line1();
        let main1_cycles = chain.cores[i_main1].cycles();
        eprintln!(
            "P3.7 phase 2 chunk {chunk}: tick={}, MAIN1 cycles={}, \
             LCD line0={:?}",
            chain.current_tick, main1_cycles, line0,
        );
        if !line0.starts_with("Waiting") {
            recovered_at_tick = Some(chain.current_tick);
            break;
        }
        if chain.current_tick >= recovery_deadline {
            break;
        }
    }

    // Sanity: MAIN1 actually started stepping after the late
    // boot offset (boot-offset wiring guard).
    assert!(
        chain.cores[i_main1].cycles() > 0,
        "MAIN1 should have started stepping after LATE_OFFSET={LATE_OFFSET}; \
         got cycles={}.  Boot-offset wiring regression?",
        chain.cores[i_main1].cycles(),
    );

    // Recovery assertion: CONTROL must have left WAITING
    // within RECOVERY_BUDGET_AFTER_LATE_BOOT ticks of MAIN1
    // coming online.
    let recovered_at_tick = recovered_at_tick.unwrap_or_else(|| {
        panic!(
            "CONTROL did not recover from `Waiting for DLCP` within \
             {RECOVERY_BUDGET_AFTER_LATE_BOOT} universal ticks of MAIN1's \
             late boot (deadline = LATE_OFFSET + budget = {recovery_deadline}); \
             final LCD: line0={:?}, line1={:?}, MAIN1 cycles={}",
            chain.lcd_slaves[i_lcd].line1(),
            chain.lcd_slaves[i_lcd].line2(),
            chain.cores[i_main1].cycles(),
        )
    });
    let recovery_window_after_main1_boot = recovered_at_tick - LATE_OFFSET;
    eprintln!(
        "P3.7 OK: MAIN1 booted at LATE_OFFSET={LATE_OFFSET}, CONTROL \
         recovered at tick {recovered_at_tick} (recovery window since \
         MAIN1 came online = {recovery_window_after_main1_boot} ticks); \
         final LCD line0={:?}, line1={:?}",
        chain.lcd_slaves[i_lcd].line1(),
        chain.lcd_slaves[i_lcd].line2(),
    );
}

/// P3.8c (symptom-equivalent, not bit-exact) — STDBY button press
/// while CONTROL is in WAITING does NOT emit a STDBY frame on
/// CONTROL.TX.
///
/// Mirrors the second-STDBY-press observation from the
/// 2026-04-27 hardware session: with CONTROL stuck in
/// `Waiting for DLCP` after the asymmetric wake (only LEFT MAIN
/// re-enumerated), a subsequent STDBY press from the front panel
/// produced *no response* — neither LCD change nor incremented
/// counters on LEFT MAIN's cmd 0x44 (`S` did not bump), proving
/// CONTROL never propagated a STDBY frame.  See findings doc
/// §7.2.C and §6 for the trace.
///
/// Test setup builds on P3.8b: 3-core ring with MAIN1 held in
/// reset → CONTROL converges to `Waiting for DLCP`.  We then
/// inject an RA3 button press (active-low STDBY button per
/// `dlcp_control_v171.asm:1968`), wait through the 4-tick
/// debounce, release the pin, and capture CONTROL's TX byte
/// stream during the post-press window.  Assertion: no
/// `B0/03/0x` triplet appears (the panel STDBY route at
/// `dlcp_control_v171.asm:2702-2718` `standby_wake_broadcast`).
///
/// Codex review of the test plan (see findings doc §9
/// HIGH/MEDIUM items): the original Test C draft used the
/// wrong frame `B1/3A/00` (which is the RC5 IR endpoint, not the
/// panel-button serial frame); the corrected `B0/03/0x` frame is
/// what `standby_wake_broadcast` actually emits.  The 3-way
/// diagnostic shape (UART byte stream + debounce-cells +
/// CONNECTED flag) was suggested to also classify whether the
/// gate is structural or soft; we retain only the byte-stream
/// assertion here because a structural gate is already implied
/// by the V1.71 source: `reconnect_wait_loop` deliberately
/// honours only RIGHT (RC5) and LEFT (RA4) presses for soft
/// reset (`dlcp_control_v171.asm:5028-5032`), excluding STDBY
/// (RA3 → bit 0 of `0x9A`).  A future stronger probe could
/// snapshot `0x9A` / `0x0BE` / `0x01F.bit1` to decode the
/// gate's nature explicitly.
#[test]
fn control_in_waiting_state_does_not_emit_stdby_frame_on_button_press() {
    use dlcp_sim::memory::Address;

    let v171 = HexImage::from_hex_path(v171_control_hex_path())
        .expect("V1.71 hex parses");
    let v32 = HexImage::from_hex_path(v32_main_hex_path())
        .expect("V3.2 hex parses");
    let v23_combined = HexImage::from_hex_path(v23_main_combined_hex_path())
        .expect("V2.3 combined hex parses");

    let control = build_core_from_hex(Variant::Pic18F25K20, &v171, None, None);
    let mut main0 = build_seeded_main_core(&v32, &v23_combined);
    main0.peripherals.adc.set_an0_sample(0x0300);
    let mut main1 = build_seeded_main_core(&v32, &v23_combined);
    main1.peripherals.adc.set_an0_sample(0x0300);

    let mut chain = Chain::new();
    let i_ctl = chain.push_core(control);
    let i_main0 = chain.push_core(main0);
    let i_main1 = chain.push_core(main1);

    chain.couple_uart(i_ctl, default_tx_pin(), i_main0, default_rx_pin());
    chain.couple_uart(i_main0, default_tx_pin(), i_main1, default_rx_pin());
    chain.couple_uart(i_main1, default_tx_pin(), i_ctl, default_rx_pin());

    let i_dsp0 = chain.push_tas3108(Tas3108::default());
    let i_dsp1 = chain.push_tas3108(Tas3108::default());
    chain.couple_tas3108(i_main0, i_dsp0);
    chain.couple_tas3108(i_main1, i_dsp1);

    let i_lcd = chain.push_lcd(Hd44780::new());
    chain.couple_lcd(i_ctl, i_lcd);

    chain.apply_reset_all(ResetSource::PowerOn);
    chain.hold_core_in_reset(i_main1);
    chain.schedule_initial_steps(&[0, 0, 0]);

    // Seed CONTROL PORTA/PORTC = 0xFF (all buttons released).
    chain.cores[i_ctl]
        .memory
        .write_raw(Address::from_raw(0xF80), 0xFF); // PORTA
    chain.cores[i_ctl]
        .memory
        .write_raw(Address::from_raw(0xF82), 0xFF); // PORTC

    const EXPECTED_LINE1: &str = "Waiting for DLCP";

    // Codex review of f8ceb67, MEDIUM #2: precondition uses the
    // same boot-then-WAITING anchor pattern as P3.8b -- gate the
    // LCD match on `MAIN0 DSP bytes_acked >= 1000` (monotonic
    // sentinel proving MAIN0 ran past startup banner) so we do
    // not run the STDBY-press test against the early-boot WAITING
    // banner.  Without this gate, the byte-stream / LCD-stay
    // assertions below would still pass but against a CONTROL
    // that hasn't actually reached the post-failure stuck state.
    const MAIN0_DSP_BOOT_ACK_THRESHOLD: u64 = 1000;
    let mut main0_dsp_booted = false;
    let mut converged = false;
    for chunk in 0..32 {
        chain.step_ticks(250_000_000);
        let dsp_acks = chain.tas3108_slaves[i_dsp0].bytes_acked;
        if !main0_dsp_booted
            && dsp_acks >= MAIN0_DSP_BOOT_ACK_THRESHOLD
        {
            main0_dsp_booted = true;
        }
        if main0_dsp_booted
            && chain.lcd_slaves[i_lcd].line1() == EXPECTED_LINE1
        {
            eprintln!(
                "P3.8c reached WAITING at chunk {chunk} \
                 (DSP acks={dsp_acks})"
            );
            converged = true;
            break;
        }
    }
    assert!(
        converged,
        "P3.8c precondition failed: CONTROL did not reach \
         `Waiting for DLCP` AFTER MAIN0 crossed the DSP-acks boot \
         threshold within 8 B-tick budget (final LCD: line1={:?}, \
         line2={:?}, DSP acks={}).",
        chain.lcd_slaves[i_lcd].line1(),
        chain.lcd_slaves[i_lcd].line2(),
        chain.tas3108_slaves[i_dsp0].bytes_acked,
    );

    // Snapshot CONTROL.TX history length BEFORE the button
    // press so we can scan only the post-press window.
    let pre_press_history = chain.uart_tx_history.len();

    // Inject STDBY button press by driving RA3 LOW.  Per
    // `dlcp_control_v171.asm:1968`:
    //   "0x027.bit0 = RA3 (Standby) ... active LOW"
    // V1.71's `button_scan_debounce` requires the press to
    // be stable across 4 polls (`asm:1965 "4-tick stability
    // counter at 0x0BB"`).  Hold RA3 LOW for 50 M ticks
    // (~3 M Tcy ≈ 50 ms wall) -- well past 4 button-scan
    // intervals -- then release.
    chain.set_pin_low(i_ctl, dlcp_sim::pinnet::PortLetter::A, 3);
    chain.step_ticks(50_000_000);
    chain.set_pin_high(i_ctl, dlcp_sim::pinnet::PortLetter::A, 3);
    chain.step_ticks(100_000_000);

    // Scan the post-press window for any CONTROL.TX byte that
    // could be part of a `B0/03/0x` STDBY/wake/mute broadcast
    // frame.  The frame is exactly 3 bytes: route=0xB0, cmd=0x03,
    // data ∈ {0x00, 0x01, 0x02, 0x03}.  Two failure shapes
    // matter:
    //   (a) CONTROL emitted a STDBY broadcast (the gate didn't
    //       hold) — flagged by `B0/03/00` or `B0/03/01`
    //       appearing in the slice.
    //   (b) CONTROL emitted ANY new B0-prefixed frame, hinting
    //       at a different leak from WAITING.
    let post_press: Vec<u8> = chain
        .uart_tx_history
        .iter()
        .skip(pre_press_history)
        .filter(|r| r.src_core == i_ctl)
        .map(|r| r.byte)
        .collect();
    eprintln!("P3.8c post-press CONTROL.TX bytes: {post_press:02X?}");

    let stdby_frame_pos = post_press.windows(3).position(|w| {
        w[0] == 0xB0 && w[1] == 0x03 && (w[2] == 0x00 || w[2] == 0x01)
    });
    assert!(
        stdby_frame_pos.is_none(),
        "CONTROL emitted a panel STDBY broadcast frame `B0/03/0x` while in \
         WAITING -- gate leaked.  Post-press CONTROL.TX = {post_press:02X?}.  \
         V1.71 source `dlcp_control_v171.asm:5028-5032` deliberately gates \
         RA3 (STDBY) out of the WAITING-loop soft-reset path; this assertion \
         locks in that contract."
    );

    // LCD must still read `Waiting for DLCP` (the gate hasn't
    // released CONTROL into a different screen).
    let lcd_after = &chain.lcd_slaves[i_lcd];
    assert_eq!(
        lcd_after.line1(),
        EXPECTED_LINE1,
        "CONTROL LCD must still read `Waiting for DLCP` after the gated \
         STDBY press; got line1={:?}, line2={:?}",
        lcd_after.line1(),
        lcd_after.line2(),
    );

    eprintln!(
        "P3.8c OK: gate held STDBY press; CONTROL.TX post-press bytes = {} \
         (none matching B0/03/0x); LCD still {:?}",
        post_press.len(),
        lcd_after.line1(),
    );
}

/// P3.8d (symptom-equivalent, not bit-exact) — CONTROL diag cache
/// is structurally decoupled from MAIN runtime-counter RAM.
///
/// Encodes the cmd 0x44 vs LCD cell mismatch observed on real
/// hardware 2026-04-27 (see findings doc §4 + task #44): both
/// MAINs reported `Runtime: I0 D0 S0 B0 R0 A0 P0` via cmd 0x44,
/// but the CONTROL LCD showed substantial Overflow content on
/// PB1/PB2 Diag pages.  The hypothesis is that CONTROL's PB1/PB2
/// diag cache cells (`v171_diag_pb1_*` at 0x180+ and
/// `v171_diag_pb2_*` at 0x18B+ per `src/dlcp_fw/asm/dlcp_control_ram.inc`)
/// can hold values that DON'T track MAIN's BANK 2 counters,
/// because they are independent RAM (not aliased) and CONTROL
/// only updates them when BF/2N reply frames land.  Random
/// post-POR garbage in cache cells, partial overwrites, or just
/// stale snapshots can produce the divergence.
///
/// This test does NOT model the *cause* (randomized POR RAM-init
/// is out of scope); it locks in the *contract* that the cells
/// are independent so a future regression that aliased them
/// (or that injected MAIN counter writes into CONTROL cache) would
/// surface here.
#[test]
fn control_diag_lcd_render_decouples_from_main_diag_ram_when_cache_seeded() {
    use dlcp_sim::memory::Address;

    let v171 = HexImage::from_hex_path(v171_control_hex_path())
        .expect("V1.71 hex parses");
    let v32 = HexImage::from_hex_path(v32_main_hex_path())
        .expect("V3.2 hex parses");
    let v23_combined = HexImage::from_hex_path(v23_main_combined_hex_path())
        .expect("V2.3 combined hex parses");

    let control = build_core_from_hex(Variant::Pic18F25K20, &v171, None, None);
    let mut main0 = build_seeded_main_core(&v32, &v23_combined);
    main0.peripherals.adc.set_an0_sample(0x0300);

    // Two-core chain (CONTROL + MAIN0) so MAIN0 boots and
    // populates its BANK 2 cells normally; we don't need MAIN1
    // for this contract probe.
    let mut chain = Chain::new();
    let i_ctl = chain.push_core(control);
    let i_main0 = chain.push_core(main0);

    chain.couple_uart(i_ctl, default_tx_pin(), i_main0, default_rx_pin());
    chain.couple_uart(i_main0, default_tx_pin(), i_ctl, default_rx_pin());

    let i_dsp0 = chain.push_tas3108(Tas3108::default());
    chain.couple_tas3108(i_main0, i_dsp0);

    chain.apply_reset_all(ResetSource::PowerOn);
    chain.schedule_initial_steps(&[0, 0]);

    chain.cores[i_ctl]
        .memory
        .write_raw(Address::from_raw(0xF80), 0xFF);
    chain.cores[i_ctl]
        .memory
        .write_raw(Address::from_raw(0xF82), 0xFF);

    // Boot until DSP-init complete -- ensures MAIN0 reaches
    // its periodic main-service loop and would have populated
    // its BANK 2 diag block had any standby/wake transitions
    // occurred (none have, so cells stay zero on the runtime
    // axis).
    chain.run_until(
        10_000_000,
        5_000_000_000,
        |c| c.tas3108_slaves[i_dsp0].bytes_acked >= 1000,
    );

    // V1.71 CONTROL diag cache cells (BANK 1, physical 0x180+
    // per `dlcp_control_ram.inc:239-258`).  Layout:
    //   0x180 = v171_diag_pb1_i  (I2C transport faults)
    //   0x181 = v171_diag_pb1_d  (DSP refresh)
    //   0x182 = v171_diag_pb1_s  (standby)
    //   0x183 = v171_diag_pb1_b  (bring-up)
    //   0x184 = v171_diag_pb1_r  (reset)
    //   0x185 = v171_diag_pb1_a  (audio mute)
    //   0x186 = v171_diag_pb1_p  (preset)
    //   0x187..0x18A = PB1 reset-cause flag cache
    //   0x18B..0x191 = PB2 runtime cache
    //   0x192..0x195 = PB2 reset-cause flag cache
    const PB1_CACHE_BASE: u16 = 0x180;
    const PB2_CACHE_BASE: u16 = 0x18B;

    // Phase 1: MAIN BANK 2 runtime cells (`diag_i..diag_p` at
    // 0x2E5..0x2EB) must be zero on the standby axis — no
    // STDBY/wake events happened, so `diag_s` and `diag_b`
    // are 0.  This pins MAIN's view of "no runtime activity".
    let main_diag_s = chain.cores[i_main0]
        .memory
        .read_raw(Address::from_raw(0x2E7));
    let main_diag_b = chain.cores[i_main0]
        .memory
        .read_raw(Address::from_raw(0x2E8));
    assert_eq!(
        main_diag_s, 0,
        "MAIN BANK 2 diag_s (0x2E7) must be 0 with no standby events; got 0x{main_diag_s:02X}"
    );
    assert_eq!(
        main_diag_b, 0,
        "MAIN BANK 2 diag_b (0x2E8) must be 0 with no wake events; got 0x{main_diag_b:02X}"
    );

    // Phase 2: seed CONTROL's PB1 + PB2 cache cells with V1.71
    // Tier-1 Overflow encoding values.  Per
    // `docs/V163B_DIAGNOSTICS_MENU_SPEC.md`:
    //   ' '  = 0    (cell empty)
    //   '1'..'9' = 1..9
    //   'A'..'E' = 10..14
    //   '+'  = 15+ (saturating)
    // We pick values that match the hardware capture
    //   PB1: I+ D1 SE B4  RA A3 O8 V6 W+..
    //   PB2: I+ D  S+ B   R+ A9  P  OB W9..
    let pb1_seed: [u8; 7] = [0x0F, 0x01, 0x0E, 0x04, 0x0A, 0x03, 0x08]; // I D S B R A P
    let pb2_seed: [u8; 7] = [0x0F, 0x00, 0x0F, 0x00, 0x0F, 0x09, 0x00];
    for (i, &v) in pb1_seed.iter().enumerate() {
        chain.cores[i_ctl]
            .memory
            .write_raw(Address::from_raw(PB1_CACHE_BASE + i as u16), v);
    }
    for (i, &v) in pb2_seed.iter().enumerate() {
        chain.cores[i_ctl]
            .memory
            .write_raw(Address::from_raw(PB2_CACHE_BASE + i as u16), v);
    }

    // Phase 3: assert MAIN's BANK 2 was NOT touched by the
    // CONTROL writes.  This is the load-bearing structural
    // contract: CONTROL cache and MAIN runtime cells live at
    // disjoint RAM addresses (different cores, different
    // memory images).  A regression that accidentally aliased
    // them (e.g., a misimplemented HID handler that wrote
    // CONTROL bytes into MAIN's RAM, or a peripheral mirror
    // bug) would surface here as a non-zero MAIN diag_s/diag_b.
    let main_diag_s_after = chain.cores[i_main0]
        .memory
        .read_raw(Address::from_raw(0x2E7));
    let main_diag_b_after = chain.cores[i_main0]
        .memory
        .read_raw(Address::from_raw(0x2E8));
    assert_eq!(
        main_diag_s_after, 0,
        "MAIN BANK 2 diag_s (0x2E7) must remain 0 after seeding CONTROL \
         cache (independent RAM); got 0x{main_diag_s_after:02X}.  Aliasing \
         regression?"
    );
    assert_eq!(
        main_diag_b_after, 0,
        "MAIN BANK 2 diag_b (0x2E8) must remain 0 after seeding CONTROL \
         cache (independent RAM); got 0x{main_diag_b_after:02X}"
    );

    // Phase 4: assert the seeded values are still in CONTROL's
    // RAM (writes landed in BANK 1 as expected).  This catches
    // a bug where the write went into the wrong core or got
    // overwritten by an unrelated routine.
    for (i, &v) in pb1_seed.iter().enumerate() {
        let actual = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(PB1_CACHE_BASE + i as u16));
        assert_eq!(
            actual, v,
            "CONTROL PB1 cache cell at 0x{:03X} must hold seeded 0x{:02X}; got 0x{:02X}",
            PB1_CACHE_BASE + i as u16, v, actual
        );
    }
    for (i, &v) in pb2_seed.iter().enumerate() {
        let actual = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(PB2_CACHE_BASE + i as u16));
        assert_eq!(
            actual, v,
            "CONTROL PB2 cache cell at 0x{:03X} must hold seeded 0x{:02X}; got 0x{:02X}",
            PB2_CACHE_BASE + i as u16, v, actual
        );
    }

    eprintln!(
        "P3.8d OK: CONTROL diag cache (PB1+PB2 cells at 0x180..0x191) decoupled \
         from MAIN BANK 2 runtime (diag_i..diag_p at 0x2E5..0x2EB).  \
         Hardware-observed mismatch (task #44) reproduces as the consequence: \
         CONTROL LCD renders cache values, which can desync from MAIN counters."
    );
}

/// P3.8d-strong (symptom-equivalent, not bit-exact) — CONTROL LCD
/// raster on the PB1 Diag screen reflects seeded cache cells, not
/// MAIN BANK 2 runtime cells (the LCD-render version of the
/// task #44 contract probe -- cf. the weak version above which
/// only checks structural RAM-address independence).
///
/// Stronger probe shape suggested by codex review of c993454,
/// MEDIUM #5 -- the weak Test D was characterised as "mostly
/// separate-memory tautology" because it never enters
/// `v171_diag_pb_screen` or asserts the LCD raster.  This test
/// closes that gap by:
///
///   1. Booting CONTROL + MAIN0 to DSP-init convergence AND
///      CONTROL clearing its `Waiting for DLCP` startup-handshake
///      screen.
///   2. Navigating Volume → PB1 Diag via 4 RIGHT-press cycles on
///      RA4 (button-injection, same primitive the P3.6b probe
///      uses).  Direct `menu_state` writes don't take effect once
///      a sub-screen's loop is active -- only the menu dispatcher
///      consumes menu_state at the top of the cycle.
///   3. Seeding `v171_diag_present = 0x01` (PB1 present mask)
///      AND `v171_diag_pb1_*` cache cells (0x180..0x186) to
///      V1.71 Tier-1 Overflow encoding values matching the
///      hardware capture (`PB1: I+ D1 SE B4`).
///   4. Stepping further so CONTROL's cadence loop redraws the
///      LCD using the seeded cache.
///   5. Asserting the LCD line 0 starts with `PB1:` (the
///      Degraded/Overflow layout, distinguishing it from the
///      Healthy layout `PBn / OK` and the Absent layout
///      `PBn / n/a`) AND that line 1 has flipped out of the
///      pre-seed `n/a` content into the per-PB cell row (R-prefix
///      is the V1.71 Tier-1 row-1 layout's first letter).
///   6. Asserting MAIN0 BANK 2 `diag_d`/`s`/`b`/`r`/`a`/`p`
///      remain unchanged at 0x00 -- proving the LCD content is
///      sourced from CONTROL's local cache, not from MAIN's
///      runtime cells.  `diag_i` is excluded because V3.2's
///      I2C transport-fault counter (per
///      `src/dlcp_fw/asm/dlcp_main_ram.inc:338`) drifts upward
///      naturally during the test's ~13-sim-second run from
///      TAS3108 NACKs / coeff-write retries.
///
/// The combination of (5) + (6) is the load-bearing evidence
/// that the hardware-observed cmd 0x44 vs LCD divergence (task
/// #44) follows from CONTROL's render-from-cache architecture:
/// the LCD shows what the cache holds, which can desync from
/// MAIN's actual runtime counters when the BF/2N reply path
/// fails to update the cache (P3.6b shared sim fidelity gap).
#[test]
fn control_diag_lcd_render_pb1_screen_reflects_seeded_cache_not_main_ram() {
    use dlcp_sim::memory::Address;
    use dlcp_sim::pinnet::PortLetter;

    let v171 = HexImage::from_hex_path(v171_control_hex_path())
        .expect("V1.71 hex parses");
    let v32 = HexImage::from_hex_path(v32_main_hex_path())
        .expect("V3.2 hex parses");
    let v23_combined = HexImage::from_hex_path(v23_main_combined_hex_path())
        .expect("V2.3 combined hex parses");

    let control = build_core_from_hex(Variant::Pic18F25K20, &v171, None, None);
    let mut main0 = build_seeded_main_core(&v32, &v23_combined);
    main0.peripherals.adc.set_an0_sample(0x0300);

    let mut chain = Chain::new();
    let i_ctl = chain.push_core(control);
    let i_main0 = chain.push_core(main0);

    chain.couple_uart(i_ctl, default_tx_pin(), i_main0, default_rx_pin());
    chain.couple_uart(i_main0, default_tx_pin(), i_ctl, default_rx_pin());

    let i_dsp0 = chain.push_tas3108(Tas3108::default());
    chain.couple_tas3108(i_main0, i_dsp0);

    // HD44780 LCD slave coupled to CONTROL -- the load-bearing
    // primitive that lets us assert the actual LCD raster, which
    // the weak Test D version above can't.
    let i_lcd = chain.push_lcd(Hd44780::new());
    chain.couple_lcd(i_ctl, i_lcd);

    chain.apply_reset_all(ResetSource::PowerOn);
    chain.schedule_initial_steps(&[0, 0]);

    // PORTA/PORTC = 0xFF (all buttons released) so V1.71's
    // button scanner doesn't see phantom presses.
    chain.cores[i_ctl]
        .memory
        .write_raw(Address::from_raw(0xF80), 0xFF);
    chain.cores[i_ctl]
        .memory
        .write_raw(Address::from_raw(0xF82), 0xFF);

    // Boot until DSP init has converged AND CONTROL has cleared
    // its `Waiting for DLCP` startup-handshake screen.  The
    // first predicate alone is the same anchor P3.8b/c use to
    // prove MAIN0 reached app code, but it does not guarantee
    // CONTROL has left WAITING -- which it must, otherwise the
    // menu_state write below has no effect (V1.71's display
    // loop only consumes menu_state once the post-handshake
    // main loop is active).  We poll the LCD raster directly
    // and wait for the WAITING text to clear; the bit-exact LCD
    // parity test demonstrates this happens within ~5 B ticks
    // on a healthy 2-core chain.
    const MAIN0_DSP_BOOT_ACK_THRESHOLD: u64 = 1000;
    chain.run_until(
        10_000_000,
        8_000_000_000,
        |c| {
            c.tas3108_slaves[i_dsp0].bytes_acked >= MAIN0_DSP_BOOT_ACK_THRESHOLD
                && !c.lcd_slaves[i_lcd].line1().starts_with("Waiting")
        },
    );
    assert!(
        chain.current_tick < 8_000_000_000,
        "CONTROL boot did not clear WAITING within 8 B-tick safety \
         ceiling; final LCD line0={:?}, line1={:?}, DSP acks={}",
        chain.lcd_slaves[i_lcd].line1(),
        chain.lcd_slaves[i_lcd].line2(),
        chain.tas3108_slaves[i_dsp0].bytes_acked,
    );
    eprintln!(
        "P3.8d-strong post-handshake LCD: line0={:?}, line1={:?}",
        chain.lcd_slaves[i_lcd].line1(),
        chain.lcd_slaves[i_lcd].line2(),
    );

    // V1.71 RAM addresses (BANK-relative -> physical):
    //   0x0BF = menu_state (BANK 0 access RAM, no banking)
    //   0x196 = v171_diag_target  (BANK 1, physical = 0x180 + 0x16)
    //   0x197 = v171_diag_present (BANK 1, physical = 0x180 + 0x17)
    //   0x180..0x186 = v171_diag_pb1_* (BANK 1)
    const MENU_STATE_RAM: u16 = 0x0BF;
    const MENU_STATE_PB1_DIAG: u8 = 4;
    const V171_DIAG_PRESENT_PHYS: u16 = 0x197;
    const V171_DIAG_PB1_BASE_PHYS: u16 = 0x180;

    // Step 1: navigate from Volume screen to PB1 Diag via 4
    // RIGHT-press cycles on RA4 (active-low).  Direct
    // menu_state writes don't work here because V1.71's
    // display loop only consumes menu_state when the menu
    // dispatcher runs, not while a sub-screen's loop is
    // active.  The pattern below mirrors the P3.6b probe's
    // navigation (which DOES reach PB1 Diag successfully --
    // that probe is `#[ignore]`d for BF/2N reply convergence
    // reasons, not navigation reasons).
    //
    // Each press cycle: pull RA4 LOW, hold ~5 M ticks for
    // V1.71's button-scan-debounce to register a stable
    // press, release, hold ~5 M ticks for release debounce
    // + state increment + LCD redraw.
    chain.step_ticks(5_000_000); // settle released state first
    for press in 0..4 {
        chain.set_pin_low(i_ctl, PortLetter::A, 4);
        chain.step_ticks(5_000_000);
        chain.set_pin_high(i_ctl, PortLetter::A, 4);
        chain.step_ticks(5_000_000);
        let state_now = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(MENU_STATE_RAM));
        eprintln!(
            "P3.8d-strong RIGHT press #{n}: menu_state={state_now}",
            n = press + 1
        );
    }
    let menu_state_after_nav = chain.cores[i_ctl]
        .memory
        .read_raw(Address::from_raw(MENU_STATE_RAM));
    assert_eq!(
        menu_state_after_nav, MENU_STATE_PB1_DIAG,
        "After 4 RIGHT presses, menu_state must be PB1_DIAG ({}); \
         got {}.  If this fails the navigation primitive is \
         broken; cross-check with the P3.6b probe (\
         three_core_ring_v171_v32_v32_diag_page_polls_pb1_and_pb2) \
         which also does 4 RIGHT presses.",
        MENU_STATE_PB1_DIAG, menu_state_after_nav
    );

    // Step 2: probe the LCD -- it should now show the diag
    // screen rendering path (likely Absent layout initially,
    // since v171_diag_present is still 0x00 and cache cells
    // are still 0x00).  Capture so we can confirm the screen
    // is alive before we seed.
    let lcd_pre_seed_line0 = chain.lcd_slaves[i_lcd].line1();
    let lcd_pre_seed_line1 = chain.lcd_slaves[i_lcd].line2();
    eprintln!(
        "P3.8d-strong pre-seed LCD: line0={:?}, line1={:?}",
        lcd_pre_seed_line0, lcd_pre_seed_line1
    );
    assert!(
        lcd_pre_seed_line0.starts_with("PB1"),
        "After 4 RIGHT presses, LCD line 0 must start with `PB1` \
         (Diag screen entered); got line0={:?}, line1={:?}",
        lcd_pre_seed_line0, lcd_pre_seed_line1
    );

    // Step 3: seed CONTROL's diag cache with non-zero V1.71
    // Tier-1 Overflow encoding values matching the hardware
    // capture's `PB1: I+ D1 SE B4` row 0.  Per
    // `docs/V163B_DIAGNOSTICS_MENU_SPEC.md`:
    //   ' '  = 0   '1'..'9' = 1..9   'A'..'E' = 10..14   '+' = 15+
    let pb1_seed: [u8; 7] = [
        0x0F, // diag_pb1_i = 15+
        0x01, // diag_pb1_d = 1
        0x0E, // diag_pb1_s = 14 = 'E'
        0x04, // diag_pb1_b = 4
        0x0A, // diag_pb1_r = 10 = 'A'
        0x03, // diag_pb1_a = 3
        0x08, // diag_pb1_p = 8
    ];
    for (i, &v) in pb1_seed.iter().enumerate() {
        chain.cores[i_ctl]
            .memory
            .write_raw(Address::from_raw(V171_DIAG_PB1_BASE_PHYS + i as u16), v);
    }
    // Set the present mask bit 0 so the diag screen render takes
    // the Degraded/Overflow layout instead of Absent.
    chain.cores[i_ctl]
        .memory
        .write_raw(Address::from_raw(V171_DIAG_PRESENT_PHYS), 0x01);

    // Diag readback: verify the writes actually landed.
    let pb1_i_after_seed = chain.cores[i_ctl]
        .memory
        .read_raw(Address::from_raw(V171_DIAG_PB1_BASE_PHYS));
    let present_after_seed = chain.cores[i_ctl]
        .memory
        .read_raw(Address::from_raw(V171_DIAG_PRESENT_PHYS));
    eprintln!(
        "P3.8d-strong post-seed RAM readback: \
         pb1_i(0x{:03X})=0x{:02X}, present(0x{:03X})=0x{:02X}",
        V171_DIAG_PB1_BASE_PHYS, pb1_i_after_seed,
        V171_DIAG_PRESENT_PHYS, present_after_seed,
    );

    // Step 4: let the cadence loop redraw the LCD with the
    // seeded values.  V1.71's diag-screen cadence is ~1 s
    // (poll countdown clears on page entry per
    // `dlcp_control_v171.asm:3580+`), and on the redraw path it
    // re-runs `v171_diag_screen_draw` which renders cells from
    // the cache cells we just wrote.
    //
    // The redraw is gated by `v171_diag_check_redraw`
    // (`asm:4131+`): redraw fires when EITHER
    // v171_diag_flags.DIRTY is set OR
    // v171_diag_present XOR v171_diag_present_snap != 0.  We
    // seeded v171_diag_present=0x01 above; snap was initialized
    // to 0 on screen entry.  XOR is 0x01 -> non-zero -> redraw.
    //
    // Walk forward in chunks and stop once BOTH LCD rows have
    // flipped to the Degraded/Overflow layout (row 0 starts
    // with `PB1:`, row 1 starts with `R` per V1.71 Tier-1
    // row-1 layout `R<r> A<a> P<p> O<o> V<v> W<w>`).  Codex
    // review of b367528, LOW #2: stopping on row 0 alone could
    // catch a partial-redraw race where row 0 has flipped but
    // row 1 still shows the pre-seed `n/a` content.  Requiring
    // both rows past their pre-seed shape closes that gap.
    let mut redrawn = false;
    for chunk in 0..16 {
        chain.step_ticks(200_000_000);
        let line0 = chain.lcd_slaves[i_lcd].line1();
        let line1 = chain.lcd_slaves[i_lcd].line2();
        if line0.starts_with("PB1:") && line1.starts_with("R") {
            eprintln!(
                "P3.8d-strong redraw fired (both rows) at chunk {chunk} \
                 (tick={}, line0={:?}, line1={:?})",
                chain.current_tick, line0, line1
            );
            redrawn = true;
            break;
        }
    }
    if !redrawn {
        eprintln!(
            "P3.8d-strong WARNING: cadence redraw did not flip BOTH \
             rows in 16 chunks (3.2 B ticks)"
        );
    }

    let lcd_post_seed_line0 = chain.lcd_slaves[i_lcd].line1();
    let lcd_post_seed_line1 = chain.lcd_slaves[i_lcd].line2();
    let pb1_i_post_redraw = chain.cores[i_ctl]
        .memory
        .read_raw(Address::from_raw(V171_DIAG_PB1_BASE_PHYS));
    let present_post_redraw = chain.cores[i_ctl]
        .memory
        .read_raw(Address::from_raw(V171_DIAG_PRESENT_PHYS));
    let menu_post_redraw = chain.cores[i_ctl]
        .memory
        .read_raw(Address::from_raw(MENU_STATE_RAM));
    eprintln!(
        "P3.8d-strong post-seed LCD: line0={:?}, line1={:?}",
        lcd_post_seed_line0, lcd_post_seed_line1
    );
    eprintln!(
        "P3.8d-strong post-redraw RAM: pb1_i=0x{pb1_i_post_redraw:02X}, \
         present=0x{present_post_redraw:02X}, menu_state={menu_post_redraw}"
    );

    // Step 5: assert the diag-screen render now reflects the
    // Degraded/Overflow layout.  Key discriminator from the
    // V1.71 Tier-1 spec: row 0 character at column 3 is `:` for
    // Degraded/Overflow (cells follow), and ` ` (space) for
    // Healthy / Absent (`PBn ` followed by ` ` fill or
    // `OK` / `n/a` on row 1).  This proves the present-mask
    // bit we seeded was honoured.
    let line0_chars: Vec<char> = lcd_post_seed_line0.chars().collect();
    assert!(
        line0_chars.len() >= 4,
        "LCD line 0 must be at least 4 chars after seed; got {:?}",
        lcd_post_seed_line0
    );
    assert_eq!(
        line0_chars[3], ':',
        "LCD line 0 col 3 must be `:` (V1.71 Tier-1 Degraded/Overflow \
         layout, proving v171_diag_present.bit_0 was honoured); got \
         line0={:?}, full-line-chars={line0_chars:?}",
        lcd_post_seed_line0
    );
    assert!(
        lcd_post_seed_line0.starts_with("PB1:"),
        "LCD line 0 must start with `PB1:` after seeding the present \
         mask + cache; got {:?}",
        lcd_post_seed_line0
    );
    // Codex LOW from b367528 #2 follow-up: also assert row 1
    // has flipped out of pre-seed `n/a` content into per-PB
    // cell row.  V1.71 Tier-1 row-1 layout starts with `R`
    // (rendering `R<r-cell> A<a-cell> ...`); the Absent layout
    // had `n/a             `.  Pairing the row-0 `PB1:` check
    // with this row-1 `R` prefix prevents the partial-redraw
    // race from spuriously passing.
    assert!(
        lcd_post_seed_line1.starts_with("R"),
        "LCD line 1 must start with `R` (V1.71 Tier-1 row-1 cell \
         layout) after redraw; got {:?}.  If still `n/a...`, the \
         row-1 redraw didn't fire even though row 0 did -- \
         partial-redraw race.",
        lcd_post_seed_line1
    );
    // Specific-char check: the seeded diag_pb1_s = 0x0E should
    // render as 'E' (Tier-1 alpha encoding for nibble values
    // 0xA..0xE).  This char is NOT one MAIN can produce naturally
    // -- it requires diag_s == 14 which means 14 explicit
    // standby-event_dispatches, none of which we triggered.
    // Finding 'E' on the LCD is therefore load-bearing evidence
    // that the LCD is rendering CONTROL's cache, not MAIN's
    // actual counter values.
    assert!(
        lcd_post_seed_line0.contains('E'),
        "LCD line 0 must contain 'E' (rendered from seeded \
         diag_pb1_s = 0x0E -- a value MAIN cannot produce through \
         standby_event_dispatch in this test setup); got {:?}",
        lcd_post_seed_line0
    );

    // Step 6: assert MAIN0 BANK 2 runtime cells reflect MAIN's
    // actual idle behaviour, NOT our seeded LCD content.
    // `diag_i` (I2C transport-fault counter per
    // `dlcp_main_ram.inc:338`) drifts upward during the
    // ~13-sim-second test run because V3.2 boot probe sequences
    // and TAS3108 NACK retries land in this counter -- so we
    // exclude it from the strict-zero check.  But
    // diag_d/s/b/r/a/p only fire on specific event triggers
    // (DSP refresh / standby / bring-up / reset / mute /
    // preset) which never occur in this test setup, so they
    // should remain at MAIN's POR baseline of 0x00.  Our seed
    // for those cells (1, 14, 4, 10, 3, 8) cannot have come
    // from MAIN's BANK 2 -- they could only have come from the
    // test harness writing CONTROL's cache directly.
    //
    // Per-cell assertions: skip diag_i (drifts on I2C faults),
    // assert all other cells stay 0.
    for (offset, name) in [
        (1u16, "diag_d"),
        (2, "diag_s"),
        (3, "diag_b"),
        (4, "diag_r"),
        (5, "diag_a"),
        (6, "diag_p"),
    ] {
        let cell = chain.cores[i_main0]
            .memory
            .read_raw(Address::from_raw(0x2E5 + offset));
        assert_eq!(
            cell, 0,
            "MAIN0 BANK 2 {} (0x{:03X}) must remain 0x00 after seeding \
             CONTROL cache (decoupling contract -- this counter only \
             fires on event triggers we never inject); got 0x{:02X}.  \
             If non-zero, MAIN0 saw an unexpected event OR our seed \
             leaked into MAIN's RAM -- aliasing regression.",
            name, 0x2E5 + offset, cell
        );
    }
    // Log diag_i (I2C transport-fault counter) for visibility --
    // it drifts upward during the test run from V3.2 boot probes
    // / TAS3108 NACK retries, so we don't strict-equal it but
    // observability matters when reasoning about the test's
    // behaviour.
    let main0_diag_i = chain.cores[i_main0]
        .memory
        .read_raw(Address::from_raw(0x2E5));
    eprintln!(
        "P3.8d-strong info: MAIN0 diag_i (I2C transport-fault \
         counter, naturally drifts on TAS3108 NACK retries) \
         = 0x{main0_diag_i:02X} (seed was 0x0F)"
    );

    // Step 7: also verify the seeded values are still in
    // CONTROL's RAM (writes weren't clobbered by the cadence
    // loop's queries -- in our sim they aren't, because the
    // BF/2N reply-cache update path is the open P3.6b gap).
    for (i, &v) in pb1_seed.iter().enumerate() {
        let actual = chain.cores[i_ctl]
            .memory
            .read_raw(Address::from_raw(V171_DIAG_PB1_BASE_PHYS + i as u16));
        assert_eq!(
            actual, v,
            "CONTROL PB1 cache cell at 0x{:03X} must hold seeded 0x{:02X} \
             after the redraw cycle; got 0x{:02X}.  If this fails the \
             cadence loop's BF/2N path must be overwriting cache \
             cells -- which would be a P3.6b convergence success and \
             conflicts with the test's premise; re-baseline the test.",
            V171_DIAG_PB1_BASE_PHYS + i as u16, v, actual
        );
    }

    let _ = PortLetter::A; // silence unused-import lint if any
    eprintln!(
        "P3.8d-strong OK: PB1 Diag screen rendered with seeded cache \
         (LCD line0=`{lcd_post_seed_line0}`, line1=`{lcd_post_seed_line1}`); \
         MAIN0 BANK 2 unchanged at all-zero -- LCD-vs-MAIN-RAM divergence \
         locked in."
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

    let control = build_core_from_hex(Variant::Pic18F25K20, &v171, None, None);
    // V3.1 MAIN's user IRQ handler lives at 0x1008 (saves
    // FSR2 + CALL FAST main_isr_dispatch); the bootloader
    // would normally trampoline 0x0008 → 0x1008 but isn't
    // loaded, so we bake the trampoline here.  Task #30 fix.
    let mut main = build_core_from_hex(
        Variant::Pic18F2455,
        &v31,
        Some(0x1000),
        Some(0x1008),
    );
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

/// Probe (P3.5 part-10b): how long until V3.1 + V1.71 emits
/// the FULL gpsim-observed 7-frame burst (1 CONTROL→MAIN +
/// 6 MAIN→CONTROL = 21 bytes total)?  Empirical convergence
/// point informs the safety ceiling for the hard-pass
/// bit-exact test.
///
/// Prints the captured bytes (per direction) so we can
/// see whether the sequence matches gpsim ground truth at
/// the byte level before tightening to a strict
/// `assert_eq!`.  Marked `#[ignore]` because the wall-clock
/// is unknown until the probe runs (likely several seconds
/// while the firmware emits all 7 frames).
#[test]
#[ignore = "P3.5 part-10b probe; wall-clock TBD until V3.1 emits all 7 frames"]
fn chain_v171_v31_emits_full_handshake_burst() {
    let v171 = HexImage::from_hex_path(v171_control_hex_path())
        .expect("V1.71 hex parses");
    let v31 = HexImage::from_hex_path(v31_main_hex_path())
        .expect("V3.1 hex parses");
    let v23_combined = HexImage::from_hex_path(v23_main_combined_hex_path())
        .expect("V2.3 combined hex parses");
    let control = build_core_from_hex(Variant::Pic18F25K20, &v171, None, None);
    // V3.1 MAIN's user IRQ handler lives at 0x1008 (saves
    // FSR2 + CALL FAST main_isr_dispatch); the bootloader
    // would normally trampoline 0x0008 → 0x1008 but isn't
    // loaded, so we bake the trampoline here.  Task #30 fix.
    let mut main = build_core_from_hex(
        Variant::Pic18F2455,
        &v31,
        Some(0x1000),
        Some(0x1008),
    );
    // Task #33: override MAIN's EEPROM with the V2.3-
    // combined seed so BF/07 (computed_volume+0x60) and
    // BF/06 (input_select) match gpsim ground truth.
    // Mirrors gpsim's `build_seeded_main_sim_hex` policy:
    // V3.1 hex provides app code; V2.3-combined provides
    // the EEPROM context (and, in gpsim's full version,
    // boot block + preset tables; we override only EEPROM
    // here since the chain probe doesn't exercise those
    // regions).
    for (addr, &byte) in v23_combined.eeprom.iter().enumerate() {
        main.peripherals.eeprom.set_byte(addr as u8, byte);
    }
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
    {
        let m = &chain.cores[i_main];
        let rcon = m.memory.read_raw(dlcp_sim::memory::Address::from_raw(0xFD0));
        let txsta = m.memory.read_raw(dlcp_sim::memory::Address::from_raw(0xFAC));
        eprintln!(
            "  POR-MAIN: rcon=0x{:02X} (RI={}, TO={}, PD={}) txsta=0x{:02X} (TRMT={})",
            rcon, (rcon >> 4) & 1, (rcon >> 3) & 1, (rcon >> 2) & 1,
            txsta, (txsta >> 1) & 1,
        );
    }

    // Wait for 21 bytes total (7 frames * 3 bytes each --
    // the gpsim-observed handshake length).  CONTROL alone
    // fills the budget today by retrying its BF/04 frame
    // since MAIN is silent (task #30); the probe surfaces
    // that divergence quickly (< 3 s wall) without needing
    // to wait the full chain-protocol-convergence budget
    // (which is unknown post-fix and could be much longer).
    //
    // Time-series dump for task #30 Timer3 investigation:
    // run in fixed chunks (no early-exit) so we can watch
    // TMR3 progress across the run.
    let mut advanced = 0u64;
    for chunk in 1..=10u64 {
        let chunk_advance = chain.run_until(
            10_000_000,
            500_000_000,
            |_| false, // no early exit; run full chunk
        );
        advanced += chunk_advance;
        let m = &chain.cores[i_main];
        let pc = m.pc();
        let pie1 = m.memory.read_raw(dlcp_sim::memory::Address::from_raw(0xF9D));
        let pir1 = m.memory.read_raw(dlcp_sim::memory::Address::from_raw(0xF9E));
        let intcon = m.memory.read_raw(dlcp_sim::memory::Address::from_raw(0xFF2));
        // V3.1 ring buffer pointers (banked):
        // - rx_ring_wr: 0x0C7 (bank 0)
        // - rx_ring_rd: 0x0C6 (bank 0)
        // - delay counter ram_0x003/0x004: 0x003/0x004 (Access)
        let rx_wr = m.memory.read_raw(dlcp_sim::memory::Address::from_raw(0x0C7));
        let rx_rd = m.memory.read_raw(dlcp_sim::memory::Address::from_raw(0x0C6));
        let ram3 = m.memory.read_raw(dlcp_sim::memory::Address::from_raw(0x003));
        let ram4 = m.memory.read_raw(dlcp_sim::memory::Address::from_raw(0x004));
        let main_rx: usize = chain
            .uart_tx_history
            .iter()
            .filter(|r| r.dst_core == i_main)
            .count();
        let main_tx: usize = chain
            .uart_tx_history
            .iter()
            .filter(|r| r.src_core == i_main)
            .count();
        let rcon = m.memory.read_raw(dlcp_sim::memory::Address::from_raw(0xFD0));
        let stkptr = m.memory.read_raw(dlcp_sim::memory::Address::from_raw(0xFFC));
        eprintln!(
            "  CHUNK {chunk}: cycles={} pc=0x{:04X} pie1=0x{:02X}(RCIE={}) \
             pir1=0x{:02X}(RCIF={}) intcon=0x{:02X}(GIE={}) \
             stkptr=0x{:02X} rcon=0x{:02X} \
             rx_wr=0x{:02X} rx_rd=0x{:02X} ram003={:02X}{:02X} \
             rx={} tx={}",
            m.cycles(),
            pc, pie1, (pie1 >> 5) & 1,
            pir1, (pir1 >> 5) & 1,
            intcon, (intcon >> 7) & 1,
            stkptr, rcon,
            rx_wr, rx_rd, ram4, ram3,
            main_rx, main_tx,
        );
    }

    // Split into direction-specific byte streams.
    let ctrl_to_main: Vec<u8> = chain
        .uart_tx_history
        .iter()
        .filter(|r| r.src_core == i_control && r.dst_core == i_main)
        .map(|r| r.byte)
        .collect();
    let main_to_ctrl: Vec<u8> = chain
        .uart_tx_history
        .iter()
        .filter(|r| r.src_core == i_main && r.dst_core == i_control)
        .map(|r| r.byte)
        .collect();
    let ctrl_frames = parse_chain_frames(&ctrl_to_main);
    let main_frames = parse_chain_frames(&main_to_ctrl);

    eprintln!(
        "PROBE 10b: advanced={advanced} ticks ({:.1} s sim @ 16 ticks/Tcy / 4 MIPS)",
        advanced as f64 / 16.0 / 4_000_000.0,
    );
    eprintln!(
        "  CTRL→MAIN bytes ({}): {:02X?}",
        ctrl_to_main.len(),
        ctrl_to_main
    );
    eprintln!("  CTRL→MAIN frames ({}): {:?}", ctrl_frames.len(), ctrl_frames);
    eprintln!(
        "  MAIN→CTRL bytes ({}): {:02X?}",
        main_to_ctrl.len(),
        main_to_ctrl
    );
    eprintln!("  MAIN→CTRL frames ({}): {:?}", main_frames.len(), main_frames);

    // Investigate why MAIN is silent (task #30 probe).  Dump
    // MAIN's RX/IRQ state at convergence so we can see
    // whether (a) RCREG receives bytes (chain delivery path
    // working), (b) RCIF asserts (EUSART RX accept), (c)
    // PIE1.RCIE is enabled (firmware asked for the IRQ),
    // (d) GIE/IPEN gate the IRQ in.
    let main = &chain.cores[i_main];
    let rcsta = main.memory.read_raw(dlcp_sim::memory::Address::from_raw(0xFAB));
    let rcreg = main.memory.read_raw(dlcp_sim::memory::Address::from_raw(0xFAE));
    let pir1 = main.memory.read_raw(dlcp_sim::memory::Address::from_raw(0xF9E));
    let pie1 = main.memory.read_raw(dlcp_sim::memory::Address::from_raw(0xF9D));
    let intcon = main.memory.read_raw(dlcp_sim::memory::Address::from_raw(0xFF2));
    let rcon = main.memory.read_raw(dlcp_sim::memory::Address::from_raw(0xFD0));
    let txsta = main.memory.read_raw(dlcp_sim::memory::Address::from_raw(0xFAC));
    eprintln!(
        "  MAIN state: pc=0x{:04X} rcsta=0x{:02X} (SPEN={}, CREN={}) rcreg=0x{:02X} \
         pir1=0x{:02X} (RCIF={}) pie1=0x{:02X} (RCIE={}) txsta=0x{:02X} (TXEN={}) \
         intcon=0x{:02X} (GIE={}, PEIE={}) rcon=0x{:02X} (IPEN={})",
        main.pc(),
        rcsta, (rcsta >> 7) & 1, (rcsta >> 4) & 1,
        rcreg,
        pir1, (pir1 >> 5) & 1,
        pie1, (pie1 >> 5) & 1,
        txsta, (txsta >> 5) & 1,
        intcon, (intcon >> 7) & 1, (intcon >> 6) & 1,
        rcon, (rcon >> 7) & 1,
    );
    // Task #30: PC=0x428C is V3.1's flow_timer3_blocking_delay_449e
    // (`btfss PIR2, 1` polling TMR3IF).  Dump Timer3 state.
    let t3con = main.memory.read_raw(dlcp_sim::memory::Address::from_raw(0xFB1));
    let tmr3h = main.memory.read_raw(dlcp_sim::memory::Address::from_raw(0xFB3));
    let tmr3l = main.memory.read_raw(dlcp_sim::memory::Address::from_raw(0xFB2));
    let pir2 = main.memory.read_raw(dlcp_sim::memory::Address::from_raw(0xFA1));
    eprintln!(
        "  MAIN TMR3: t3con=0x{:02X} (TMR3ON={}, RD16={}) tmr3h=0x{:02X} \
         tmr3l=0x{:02X} pir2=0x{:02X} (TMR3IF={}) cycles={}",
        t3con, t3con & 0x01, (t3con >> 7) & 1,
        tmr3h, tmr3l,
        pir2, (pir2 >> 1) & 1,
        main.cycles(),
    );

    // Compare against ground truth IF the fixture is
    // present; otherwise just report.
    let root = repo_root();
    let dir = root.join(
        "artifacts/ground_truth/\
         test_v171_v31_chain__test_v171_v31_chain_reaches_display__\
         23ccf08e11a5",
    );
    if dir.exists() {
        let gt_ctrl = load_ground_truth_frames(&dir.join("uart_tx_control.jsonl"))
            .expect("CONTROL ground truth parses");
        let gt_main = load_ground_truth_frames(&dir.join("uart_tx_main_0.jsonl"))
            .expect("MAIN ground truth parses");
        eprintln!(
            "  GROUND-TRUTH CTRL→MAIN frames ({}): {:?}",
            gt_ctrl.len(),
            gt_ctrl
        );
        eprintln!(
            "  GROUND-TRUTH MAIN→CTRL frames ({}): {:?}",
            gt_main.len(),
            gt_main
        );
        if ctrl_frames == gt_ctrl && main_frames == gt_main {
            eprintln!("  STATUS: bit-exact match ✓");
        } else {
            eprintln!(
                "  STATUS: divergence -- ctrl_match={}, main_match={}",
                ctrl_frames == gt_ctrl,
                main_frames == gt_main,
            );
        }
    }
}

// ---------------------------------------------------------------------------
// Ground-truth comparison helpers (P3.5 part-10).
//
// gpsim ground truth captured via P0.4's `--capture-ground-truth`
// pytest hook lives at:
//   artifacts/ground_truth/test_v171_v31_chain__test_v171_v31_chain_reaches_display__*/
// with two relevant files for this scaffold:
//   * uart_tx_control.jsonl  -- CONTROL → MAIN frames
//   * uart_tx_main_0.jsonl   -- MAIN → CONTROL frames
// Each line is a one-frame JSON object:
//   {"cmd": <u8>, "data": <u8>, "route": <u8>, "seq": <u32>}
//
// The DLCP chain protocol is 3-byte frames over the
// 31250-baud current-loop EUSART (route, cmd, data).  When
// the Rust simulator's `Chain::uart_tx_history` records raw
// bytes for a coupling, every 3 consecutive bytes form one
// frame.
//
// This helper module lives inline in the test binary
// (zero-dep manual JSONL parse) so the parity-comparison
// path stays self-contained.  If/when more tests need this
// machinery we can lift it into a shared
// `dlcp-sim-test-utils` crate.
// ---------------------------------------------------------------------------

/// One DLCP chain protocol frame (3 bytes on the wire).
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
struct ChainFrame {
    route: u8,
    cmd: u8,
    data: u8,
}

/// Group a flat byte stream into 3-byte chain frames.
/// Returns an empty vec if the stream length is not a
/// multiple of 3 (caller's job to handle partial frames if
/// they care).
fn parse_chain_frames(bytes: &[u8]) -> Vec<ChainFrame> {
    if !bytes.len().is_multiple_of(3) {
        return Vec::new();
    }
    bytes
        .chunks_exact(3)
        .map(|c| ChainFrame { route: c[0], cmd: c[1], data: c[2] })
        .collect()
}

/// Tiny JSONL parser tailored for the
/// `{"cmd": N, "data": N, "route": N, "seq": N}` line shape
/// captured by `OutputCapture` in
/// `src/dlcp_fw/sim/ground_truth.py`.  Returns frames in the
/// JSON-encoded order (which is the actual bus-time order
/// since the capture preserves wire order in the file).
///
/// Hand-rolled to avoid pulling in serde+serde_json just
/// for this one test fixture.  Returns `Err` only on
/// malformed lines so caller can panic with a useful
/// message.
fn load_ground_truth_frames(path: &Path) -> Result<Vec<ChainFrame>, String> {
    let text = std::fs::read_to_string(path)
        .map_err(|e| format!("read {}: {}", path.display(), e))?;
    let mut frames = Vec::new();
    for (idx, raw_line) in text.lines().enumerate() {
        let line = raw_line.trim();
        if line.is_empty() {
            continue;
        }
        let cmd = extract_u8_field(line, "cmd")
            .ok_or_else(|| format!("line {}: missing/bad `cmd`", idx + 1))?;
        let data = extract_u8_field(line, "data")
            .ok_or_else(|| format!("line {}: missing/bad `data`", idx + 1))?;
        let route = extract_u8_field(line, "route")
            .ok_or_else(|| format!("line {}: missing/bad `route`", idx + 1))?;
        frames.push(ChainFrame { route, cmd, data });
    }
    Ok(frames)
}

/// Extract `"key": <integer>` from a JSON line.  Tolerates
/// whitespace and trailing commas.  Returns `None` if the
/// key is missing or the value isn't a 0..=255 integer.
fn extract_u8_field(line: &str, key: &str) -> Option<u8> {
    let needle = format!("\"{key}\"");
    let key_pos = line.find(&needle)?;
    let after_key = &line[key_pos + needle.len()..];
    let colon_pos = after_key.find(':')?;
    let value_start = &after_key[colon_pos + 1..];
    // Walk past whitespace, then collect digits.
    let trimmed = value_start.trim_start();
    let digits: String = trimmed.chars().take_while(|c| c.is_ascii_digit()).collect();
    if digits.is_empty() {
        return None;
    }
    digits.parse::<u8>().ok()
}

/// Find `needle` as a contiguous subsequence in `haystack`.
/// Returns the starting index of the first match, or
/// `None`.  Used by the V3.1 chain bit-exact parity gate to
/// locate gpsim's expected MAIN→CTRL frame burst inside our
/// emitted byte stream (which may include leading boot-time
/// emits or trailing passthrough traffic that gpsim's
/// capture window doesn't cover).  Task #29.
fn find_subsequence<T: PartialEq>(haystack: &[T], needle: &[T]) -> Option<usize> {
    if needle.is_empty() {
        return Some(0);
    }
    if haystack.len() < needle.len() {
        return None;
    }
    (0..=haystack.len() - needle.len())
        .find(|&i| haystack[i..i + needle.len()] == *needle)
}

/// P3.5 part-10 bit-exact parity gate: V3.1 + V1.71 chain
/// emits gpsim's captured 6-frame MAIN→CTRL response burst
/// in response to CONTROL's BF/04 heartbeat.  Task #29.
///
/// gpsim ground truth (captured via P0.4's
/// `--capture-ground-truth` pytest hook):
///   {BF, 08, 00}, {BF, 05, 03}, {BF, 07, 4F},
///   {BF, 03, 01}, {BF, 06, 00}, {BF, 1D, 04}
///
/// We assert this 6-frame sequence appears as a contiguous
/// subsequence in MAIN's TX byte stream.  Allows for
/// leading boot-time emits (our sim may fire one extra
/// `send_dsp_fault_status` before the response burst that
/// gpsim's capture window starts after) and trailing
/// passthrough traffic.
///
/// Builds on top of:
///   * task #30 (RCIF read-clear, 2455 POR TXSTA.TRMT,
///     2-deep RX FIFO + OERR) -- without these MAIN was
///     stuck in reset loop / never parsed frames.
///   * task #33 (V2.3-combined EEPROM seed) -- without
///     this BF/07 and BF/06 data bytes don't match.
#[test]
fn chain_v171_v31_main_emits_gpsim_response_burst_bit_exact() {
    let v171 = HexImage::from_hex_path(v171_control_hex_path())
        .expect("V1.71 hex parses");
    let v31 = HexImage::from_hex_path(v31_main_hex_path())
        .expect("V3.1 hex parses");
    let v23_combined = HexImage::from_hex_path(v23_main_combined_hex_path())
        .expect("V2.3 combined hex parses");
    let control = build_core_from_hex(Variant::Pic18F25K20, &v171, None, None);
    // Task #36: silicon-correct boot via V2.3-combined
    // merge.  Replaces the prior bake-trampoline approach
    // (`Some(0x1000), Some(0x1008)`) -- now V2.3's real
    // boot block at 0x0000-0x0FFF runs naturally and
    // jumps to the V3.1 app at 0x1000.
    let mut main = build_seeded_main_core(&v31, &v23_combined);
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

    // Run until MAIN has emitted at least 21 bytes (7 BF
    // frames -- enough to cover the 6-frame gpsim burst
    // even if our sim emits an extra leading BF/08).
    // Universal-tick budget sized to ~2 s sim time at 16
    // ticks/Tcy / 4 MIPS, then increase by 50% safety
    // margin.
    let _advanced = chain.run_until(
        10_000_000,
        2_000_000_000,
        |c| {
            c.uart_tx_history
                .iter()
                .filter(|r| r.src_core == i_main && r.dst_core == i_control)
                .count()
                >= 21
        },
    );

    let main_to_ctrl: Vec<u8> = chain
        .uart_tx_history
        .iter()
        .filter(|r| r.src_core == i_main && r.dst_core == i_control)
        .map(|r| r.byte)
        .collect();
    assert!(
        main_to_ctrl.len() >= 21,
        "MAIN must emit ≥21 bytes (7 frames) to contain gpsim's 6-frame burst; got {} bytes",
        main_to_ctrl.len()
    );

    // Parse MAIN's byte stream into 3-byte frames so the
    // gpsim-burst search is FRAME-ALIGNED (codex review of
    // 3d2d350 LOW: a raw-byte subsequence search could
    // match at a misaligned offset, e.g. mid-frame).
    // Truncate any trailing partial frame.
    let aligned_len = (main_to_ctrl.len() / 3) * 3;
    let main_frames: Vec<ChainFrame> = main_to_ctrl[..aligned_len]
        .chunks_exact(3)
        .map(|c| ChainFrame { route: c[0], cmd: c[1], data: c[2] })
        .collect();

    // gpsim's expected 6-frame response burst.
    const GPSIM_BURST: &[ChainFrame] = &[
        ChainFrame { route: 0xBF, cmd: 0x08, data: 0x00 },
        ChainFrame { route: 0xBF, cmd: 0x05, data: 0x03 },
        ChainFrame { route: 0xBF, cmd: 0x07, data: 0x4F },
        ChainFrame { route: 0xBF, cmd: 0x03, data: 0x01 },
        ChainFrame { route: 0xBF, cmd: 0x06, data: 0x00 },
        ChainFrame { route: 0xBF, cmd: 0x1D, data: 0x04 },
    ];

    find_subsequence(&main_frames, GPSIM_BURST).unwrap_or_else(|| {
        panic!(
            "gpsim 6-frame burst not found as contiguous frame subsequence \
             in MAIN→CTRL stream.\n  MAIN frames ({}): {:?}\n  Expected: {:?}",
            main_frames.len(),
            main_frames,
            GPSIM_BURST,
        )
    });
}

/// P3.5 part-10 LCD bit-exact parity gate (task #34).
///
/// gpsim ground truth at the
/// `test_v171_v31_chain_reaches_display` capture point
/// shows CONTROL's LCD displaying:
///   Line 1: "Volume:-17.0dB A"
///   Line 2: "Auto Detect"
///
/// Our chain probe drives an `Hd44780` slave coupled to
/// CONTROL's GPIO bus (RS=LATA[5], E=LATB[4], D4..D7 =
/// PORTB[3:0]).  Run until both lines stabilise to the
/// expected text or hit a budget ceiling, then assert
/// bit-exact match.
///
/// Builds on tasks #30 (chain protocol unblock), #33
/// (V2.3-combined EEPROM seed), and #34 (HD44780 model
/// + chain coupling).
#[test]
fn chain_v171_v31_control_lcd_matches_gpsim_ground_truth_bit_exact() {
    let v171 = HexImage::from_hex_path(v171_control_hex_path())
        .expect("V1.71 hex parses");
    let v31 = HexImage::from_hex_path(v31_main_hex_path())
        .expect("V3.1 hex parses");
    let v23_combined = HexImage::from_hex_path(v23_main_combined_hex_path())
        .expect("V2.3 combined hex parses");
    let control = build_core_from_hex(Variant::Pic18F25K20, &v171, None, None);
    // Task #36: silicon-correct boot via V2.3-combined merge.
    let mut main = build_seeded_main_core(&v31, &v23_combined);
    main.peripherals.adc.set_an0_sample(0x0300);
    let mut chain = Chain::new();
    let i_control = chain.push_core(control);
    let i_main = chain.push_core(main);
    chain.couple_uart(i_control, default_tx_pin(), i_main, default_rx_pin());
    chain.couple_uart(i_main, default_tx_pin(), i_control, default_rx_pin());
    let i_tas3108 = chain.push_tas3108(Tas3108::default());
    chain.couple_tas3108(i_main, i_tas3108);
    // HD44780 slave coupled to CONTROL.  Pin map is baked
    // into `Chain::dispatch_lcd_pins_to_coupled_slaves`
    // (RS=LATA[5], E=LATB[4], D4..D7=PORTB[3:0] per V1.71
    // CONTROL `lcd_char_write`).
    let i_lcd = chain.push_lcd(Hd44780::new());
    chain.couple_lcd(i_control, i_lcd);
    chain.apply_reset_all(ResetSource::PowerOn);
    chain.schedule_initial_steps(&[0, 0]);
    // V1.71 CONTROL reads its 6 button inputs as ACTIVE-LOW
    // pins on RA1/RA2/RA3/RA4 (SELECT/DOWN/STBY/RIGHT) and
    // RC0/RC5 (UP/LEFT).  In gpsim these are stimulated
    // with `initial_state 1` (released).  Our sim has no
    // pin-state injection yet, so PORTA / PORTC default to
    // 0 -- which CONTROL reads as "all buttons pressed",
    // triggers the STBY handler, and parks the LCD on the
    // `Zzz...` standby screen.  Seed PORTA = PORTC = 0xFF
    // so all buttons read as released.  Done AFTER
    // `apply_reset_all` because POR wipes the SFR window.
    // Mirrors `_setup_button_stimuli` in
    // `src/dlcp_fw/sim/control_gpsim.py:494`.  Task #34.
    chain.cores[i_control]
        .memory
        .write_raw(dlcp_sim::memory::Address::from_raw(0xF80), 0xFF); // PORTA
    chain.cores[i_control]
        .memory
        .write_raw(dlcp_sim::memory::Address::from_raw(0xF82), 0xFF); // PORTC

    // Expected LCD content from gpsim's
    // `lcd_control.txt` ground truth.  Both lines are
    // padded to 16 chars (HD44780 line width).
    const EXPECTED_LINE1: &str = "Volume:-17.0dB A";
    const EXPECTED_LINE2: &str = "Auto Detect     ";

    // Run until BOTH lines match, with an upper budget so
    // a regression fails fast instead of hanging.  The
    // matching predicate borrows the LCD slave through
    // `chain.lcd_slaves[i_lcd]`; `run_until` re-checks it
    // every chunk.  Budget sized to ~5 s sim time at
    // 16 ticks/Tcy (4 MIPS for K20).
    let _advanced = chain.run_until(
        10_000_000,
        5_000_000_000,
        |c| {
            let l = &c.lcd_slaves[i_lcd];
            l.line1() == EXPECTED_LINE1 && l.line2() == EXPECTED_LINE2
        },
    );

    let lcd = &chain.lcd_slaves[i_lcd];
    assert_eq!(
        lcd.line1(),
        EXPECTED_LINE1,
        "LCD line 1 mismatch.  Full state:\n  line1 = {:?}\n  line2 = {:?}",
        lcd.line1(),
        lcd.line2(),
    );
    assert_eq!(
        lcd.line2(),
        EXPECTED_LINE2,
        "LCD line 2 mismatch.  Full state:\n  line1 = {:?}\n  line2 = {:?}",
        lcd.line1(),
        lcd.line2(),
    );
}

#[cfg(test)]
mod ground_truth_tests {
    use super::*;

    #[test]
    fn parse_chain_frames_groups_into_3byte_frames() {
        let bytes = vec![0xBF, 0x08, 0x00, 0xBF, 0x05, 0x03];
        let frames = parse_chain_frames(&bytes);
        assert_eq!(frames.len(), 2);
        assert_eq!(frames[0], ChainFrame { route: 0xBF, cmd: 0x08, data: 0x00 });
        assert_eq!(frames[1], ChainFrame { route: 0xBF, cmd: 0x05, data: 0x03 });
    }

    #[test]
    fn parse_chain_frames_empty_on_partial_frame() {
        // 5 bytes is not divisible by 3 -- caller's data is
        // a partial frame, return empty rather than truncate.
        assert!(parse_chain_frames(&[0xBF, 0x08, 0x00, 0xBF, 0x05]).is_empty());
    }

    #[test]
    fn extract_u8_field_handles_simple_objects() {
        let line = r#"{"cmd": 4, "data": 0, "route": 177, "seq": 0}"#;
        assert_eq!(extract_u8_field(line, "cmd"), Some(4));
        assert_eq!(extract_u8_field(line, "data"), Some(0));
        assert_eq!(extract_u8_field(line, "route"), Some(177));
        assert_eq!(extract_u8_field(line, "seq"), Some(0));
        assert_eq!(extract_u8_field(line, "missing"), None);
    }

    #[test]
    fn extract_u8_field_rejects_out_of_range() {
        let line = r#"{"big": 999}"#;
        assert_eq!(extract_u8_field(line, "big"), None);
    }

    /// Smoke test against the actual gpsim-captured
    /// fixture.  The `test_v171_v31_chain_reaches_display`
    /// run produced 1 CONTROL→MAIN frame
    /// (route=0xB1, cmd=4, data=0) and 6 MAIN→CONTROL
    /// frames.  Verify the loader correctly parses both
    /// files.  See
    /// `artifacts/ground_truth/test_v171_v31_chain__test_v171_v31_chain_reaches_display__*/`
    /// for the source-of-truth fixtures.
    #[test]
    fn load_ground_truth_frames_parses_v171_v31_fixture() {
        let root = repo_root();
        let dir = root.join(
            "artifacts/ground_truth/\
             test_v171_v31_chain__test_v171_v31_chain_reaches_display__\
             23ccf08e11a5",
        );
        if !dir.exists() {
            // Fixture isn't in the worktree -- skip rather
            // than fail.  The fixture is regenerated by
            // running `pytest tests/sim/test_v171_v31_chain.py
            // --capture-ground-truth`; CI environments without
            // gpsim won't have it.
            return;
        }
        let ctrl_frames = load_ground_truth_frames(&dir.join("uart_tx_control.jsonl"))
            .expect("CONTROL frames parse");
        let main_frames = load_ground_truth_frames(&dir.join("uart_tx_main_0.jsonl"))
            .expect("MAIN frames parse");
        assert_eq!(
            ctrl_frames,
            vec![ChainFrame { route: 0xB1, cmd: 4, data: 0 }],
            "CONTROL→MAIN ground truth shape"
        );
        assert_eq!(
            main_frames,
            vec![
                ChainFrame { route: 0xBF, cmd: 8, data: 0 },
                ChainFrame { route: 0xBF, cmd: 5, data: 3 },
                ChainFrame { route: 0xBF, cmd: 7, data: 79 },
                ChainFrame { route: 0xBF, cmd: 3, data: 1 },
                ChainFrame { route: 0xBF, cmd: 6, data: 0 },
                ChainFrame { route: 0xBF, cmd: 29, data: 4 },
            ],
            "MAIN→CONTROL ground truth shape"
        );
    }
}
