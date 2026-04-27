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
use dlcp_sim::core::Core;
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
        if v3_app.flash_present[addr] {
            flash[addr] = v3_app.flash[addr];
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
    let expected_uart_edges = [
        (i_ctl, i_main0),
        (i_main0, i_main1),
        (i_main1, i_ctl),
    ];
    assert_eq!(
        chain.pinnet.uart.len(),
        expected_uart_edges.len(),
        "ring must have exactly 3 UART couplings, got {}",
        chain.pinnet.uart.len(),
    );
    for (idx, expected) in expected_uart_edges.iter().enumerate() {
        let actual = (
            chain.pinnet.uart[idx].src_core,
            chain.pinnet.uart[idx].dst_core,
        );
        assert_eq!(
            actual, *expected,
            "ring edge {idx} mismatch: got {actual:?}, expected {expected:?}"
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

/// P3.6 step 2 PROBE -- non-converging.  Documents the
/// current divergence: `v171_diag_present` reaches `0x01`
/// (PB1 reply landed) but never `0x03` (PB1 + PB2).  Same
/// symptom the Python harness logs in
/// `tests/sim/test_v171_v32_layer5_diag_chain.py:166`,
/// even though the Rust sim's silicon-correct ring has no
/// bridge-style echo loop.
///
/// Empirical state at exit (10 B-tick ceiling, 148 s wall):
///   * `v171_diag_present = 0x01` (PB1 only)
///   * `v171_diag_target  = 0x01` (CONTROL next-queries PB2)
///   * `menu_state        = 4`    (PB1 Diag, as set)
///   * `main0_pc          = 0x4456`
///   * `main1_pc          = 0x1872`
///   * 2105 UART deliveries during the polling window
///
/// Working hypotheses (all unconfirmed):
///   1. Same-tick UART seq-order race (task #19): MAIN0
///      forwards PB2 query to MAIN1 and MAIN1's TSR-complete
///      fire at the same universal tick; non-deterministic
///      dispatch order may strand MAIN1 mid-reply.
///   2. V3.2 MAIN forward-path firmware: cmd 0x23/0x24 (PB2)
///      may have a frame-handling subtlety that the chain
///      has to satisfy to elicit a reply (versus cmd
///      0x21/0x22 (PB1) which works).  Worth a focused look
///      at `dlcp_main_v32.asm`'s BF/2N parser before
///      assuming a sim bug.
///   3. Hidden peripheral fidelity gap surfaced only by
///      the longer chain (e.g., RCREG FIFO depth, RCIF
///      latch under back-to-back MAIN0->MAIN1 traffic).
///
/// What this probe DOES prove:
///   * The 3-core ring under V1.71+V3.2+V3.2 boots, runs
///     the diag-poll state machine, exchanges 2k+ UART
///     bytes through the silicon ring, and lands PB1 reply
///     correctly.
///   * No record in `uart_tx_history` is a self-loop --
///     the gpsim bridge echo is structurally absent (this
///     is the half of Task #22 the Rust rewrite has
///     genuinely retired).
///
/// `#[ignore]`d so the routine suite stays fast; budget
/// is 2 B ticks (was 10 B during the discovery probe) so
/// each manual iteration completes in ~30 s wall.
#[test]
#[ignore = "P3.6 step 2 probe; PB2 reply never lands -- diverging investigation needed (see docstring)"]
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

    // Stage 2: force CONTROL onto the PB1 Diag screen.
    // Real hardware reaches this via two RIGHT button
    // presses; in the absence of GPIO input modeling
    // (task #35) we poke the menu-state RAM directly.
    chain.cores[i_ctl]
        .memory
        .write_raw(Address::from_raw(MENU_STATE_RAM), MENU_STATE_PB1_DIAG);

    // Stage 3: run until both PB-reply bits land in
    // v171_diag_present.  Budget was 10 B during the
    // discovery probe; trimmed to 2 B (~16 s simulated,
    // ~30 s wall) since we know convergence does NOT
    // happen -- per the docstring above, present saturates
    // at 0x01.  Smaller budget = faster iteration when
    // investigating root cause.
    chain.run_until(
        50_000_000, // 50 M = ~350 ms wall per chunk
        2_000_000_000,
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
