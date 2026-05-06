//! PyO3 wrapper crate for `dlcp-sim`.
//!
//! P4.1 (commit 45b041d) established the minimum-viable
//! Python extension module: `import dlcp_sim_native` +
//! `__version__`.  P4.2 (this commit) adds:
//!
//!   * `Chain` -- PyO3 class wrapping
//!     `dlcp_sim::chain::Chain` plus the minimum surface
//!     the spec §3 sketch requires for the verify command:
//!         Chain.from_v171_v32()
//!         chain.step_ticks(N)
//!         chain.lcd_lines()
//!   * `_build_v171_v32_chain` -- the boilerplate that
//!     mirrors the test harness in `multicore_parity.rs`'s
//!     `three_core_ring_v171_v32_v32_*` setups: load V1.71
//!     CONTROL hex + V3.2 MAIN hex + V2.3-combined seed,
//!     build a CONTROL core + 2 MAIN cores (each with the
//!     V3.2-app-on-V2.3-seed flash merge per task #36),
//!     wire a 3-core UART ring, attach a TAS3108 DSP slave
//!     to each MAIN, attach an HD44780 LCD slave to
//!     CONTROL, apply POR reset, schedule initial steps.
//!
//! Subsequent P4.x sub-tasks (test migration) will reveal
//! which other Chain methods need binding (e.g.
//! `tx_history`, `read_ram(core, addr)`, `set_pin_*`,
//! `apply_reset_all`, etc.) and grow this module
//! incrementally.

use pyo3::exceptions::{PyKeyError, PyNotImplementedError, PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use std::path::PathBuf;

use dlcp_sim::chain::Chain as RustChain;
use dlcp_sim::core::{Core, CoreLoadOptions, core_from_hex_image};
use dlcp_sim::hex::HexImage;
use dlcp_sim::lcd::Hd44780;
use dlcp_sim::memory::Variant;
use dlcp_sim::peripherals::src4382::Src4382;
use dlcp_sim::peripherals::tas3108::Tas3108;
use dlcp_sim::pinnet::{PortLetter, default_rx_pin, default_tx_pin};
use dlcp_sim::reset::ResetSource;

/// Path to the project root (the `analysis-sim-rewrite-rust`
/// directory) at compile time.  Resolved from
/// `CARGO_MANIFEST_DIR` -- which points at
/// `<root>/crates/dlcp-sim-py` -- by walking up two parents.
fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("CARGO_MANIFEST_DIR has a parent (`crates/`)")
        .parent()
        .expect("`crates/` has a parent (the workspace root)")
        .to_path_buf()
}

fn v171_control_hex_path() -> PathBuf {
    repo_root().join("firmware/patched/releases/DLCP_Control_V1.71.hex")
}

fn v32_main_hex_path() -> PathBuf {
    repo_root().join("firmware/patched/releases/DLCP_Firmware_V3.2.hex")
}

fn v23_main_combined_hex_path() -> PathBuf {
    repo_root().join("firmware/stock/main/DLCP Firmware V2.3-combined.hex")
}

/// Stock V1.6b CONTROL hex (PIC18F25K20).  Source of the
/// V1.7 byte-identical rebuild; behavioural baseline for
/// `tests/sim/test_v17_chain.py`.
fn v16b_control_hex_path() -> PathBuf {
    repo_root().join("firmware/stock/control/DLCP Control Firmware V1.6b.hex")
}

/// V3.1 MAIN canonical release hex (PIC18F2455, app-only).
/// Used by `tests/sim/test_v171_v31_chain.py`'s V1.71+V3.1
/// pairing.  Like V3.2 it leaves `[0x0000, 0x1000)` erased
/// (the Microchip USB bootloader window), so callers must
/// merge it onto a full-silicon V2.3-combined seed before
/// running -- see `build_v17_v3x_chain_single_main`.
fn v31_main_hex_path() -> PathBuf {
    repo_root().join("firmware/patched/releases/DLCP_Firmware_V3.1.hex")
}

/// V3.x app-code patch range.  Mirror of
/// `multicore_parity.rs:113-114` (which itself mirrors
/// gpsim's `MAIN_APP_PATCH_START` / `MAIN_APP_PATCH_LIMIT`).
const MAIN_APP_PATCH_START: usize = 0x1000;
const MAIN_APP_PATCH_LIMIT: usize = 0x5600;

/// Merge a V3.x app-only hex onto a V2.3-combined seed
/// flash, returning the combined image.  Mirror of
/// `multicore_parity.rs:143::build_seeded_main_flash`.
/// Task #36's silicon-correct boot path.
fn build_seeded_main_flash(
    v3_app: &HexImage,
    v23_seed: &HexImage,
) -> Box<[u8; dlcp_sim::hex::FLASH_BYTES]> {
    let mut flash = v23_seed.flash.clone();
    let app_end = MAIN_APP_PATCH_LIMIT.min(v3_app.flash.len());
    for addr in MAIN_APP_PATCH_START..app_end {
        if let Some(byte) = v3_app.byte_at(addr) {
            flash[addr] = byte;
        }
    }
    flash
}

/// Build a silicon-correct MAIN core from a V3.x app hex
/// merged onto a V2.3-combined seed.  Mirror of
/// `multicore_parity.rs:166::build_seeded_main_core`.
fn build_seeded_main_core(v3_app: &HexImage, v23_seed: &HexImage) -> Core {
    let mut core = core_from_hex_image(Variant::Pic18F2455, v3_app, CoreLoadOptions::default());
    core.flash_mut()
        .copy_from_slice(&*build_seeded_main_flash(v3_app, v23_seed));
    for (addr, &byte) in v23_seed.eeprom.iter().enumerate() {
        core.peripherals.eeprom.set_byte(addr as u8, byte);
    }
    core
}

/// Build a CONTROL (K20) core from a V1.71 hex.  Mirror
/// of `multicore_parity.rs:227::build_core_from_hex` for
/// the K20 path: copy flash, EEPROM, CONFIG, and USER_ID byte-for-byte
/// (including 0xFF "erased" bytes -- firmware
/// distinguishes 0xFF-erased from 0x00-default at runtime
/// via "uninitialized" sentinel checks).
fn build_v171_control_core(v171: &HexImage) -> Core {
    core_from_hex_image(Variant::Pic18F25K20, v171, CoreLoadOptions::default())
}

/// Build a stock V2.3 MAIN core from V2.3-combined.  Unlike
/// V3.x, V2.3-combined ships the FULL silicon image (boot
/// block + V2.3 app + EEPROM + preset tables) -- no merge
/// or `bake_goto` trampolines needed.
fn build_stock_v23_main_core(v23_combined: &HexImage) -> Core {
    core_from_hex_image(
        Variant::Pic18F2455,
        v23_combined,
        CoreLoadOptions::default(),
    )
}

/// Top-level helper: build a 3-core ring (V1.71 CONTROL +
/// V3.2 MAIN0 + V3.2 MAIN1) wired with UART, DSP slaves,
/// and LCD slave, ready for `step_ticks`.  Mirror of the
/// chain-construction prelude in
/// `multicore_parity.rs::three_core_ring_v171_v32_v32_*`
/// scenarios.  Returns the chain plus the core / lcd /
/// dsp indices the caller may use for read access.
struct V171V32ChainHandle {
    chain: RustChain,
    i_ctl: usize,
    i_main0: usize,
    i_main1: usize,
    i_lcd: usize,
    #[allow(dead_code)]
    i_dsp0: usize,
    #[allow(dead_code)]
    i_dsp1: usize,
}

/// Single-MAIN topology handle returned by
/// `build_v17_chain_single_main` -- 1 CONTROL + 1 MAIN +
/// LCD/DSP slaves.  Mirror of the Rust prereq test
/// `chain_v16b_v23_stock_reaches_volume_screen` in
/// `multicore_parity.rs`.
struct V17SingleMainHandle {
    chain: RustChain,
    i_ctl: usize,
    i_main: usize,
    i_lcd: usize,
    #[allow(dead_code)]
    i_dsp: usize,
}

fn release_control_buttons(chain: &mut RustChain, control_idx: usize) {
    for (port, bit) in [
        (PortLetter::A, 1),
        (PortLetter::A, 2),
        (PortLetter::A, 3),
        (PortLetter::A, 4),
        (PortLetter::C, 0),
        (PortLetter::C, 5),
    ] {
        chain.set_pin_high(control_idx, port, bit);
    }
}

/// Build a 2-core chain (1 CONTROL/K20 + 1 MAIN/2455) with
/// bidirectional UART, TAS3108 DSP slave on MAIN, HD44780
/// LCD slave on CONTROL.  POR-reset, initial steps scheduled
/// at tick 0.  CONTROL button pins are externally released
/// through the GPIO injection API; AN0 ADC sample seeded to
/// 0x0300 (mid-rail mains-detect).
///
/// `control_hex_path` accepts any K20 hex (V1.6b stock,
/// V1.7 byte-identical rebuild, V1.7 shifted, V1.71, etc.).
///
/// `main_hex_path` MUST be a full-silicon 2455 image (boot
/// block + app + EEPROM), e.g. V2.3-combined.  The builder
/// copies the entire flash directly via `core.flash_mut().
/// copy_from_slice` -- no merge or `bake_goto`-trampoline
/// step is applied.  App-only hexes (V3.x releases, which
/// leave `[0x0000, 0x1000)` erased because the Microchip
/// USB bootloader owns that window) would cold-boot into a
/// `0xFFFF`-filled reset vector; `0xFFFF` decodes as
/// `NopContinuation` (executor: `crates/dlcp-sim/src/exec.rs`
/// silently advances PC by 2 each Tcy), so the core does
/// not fault -- it walks 0x0000-0x0FFF as NOPs and
/// eventually hits whatever bytes follow at the start of
/// the patched app code.  In V3.x's case that's the shipped
/// `GOTO 0x1014` at flash offset 0x1000, which skips the
/// V3.x user-IRQ handler at 0x1008 entirely and re-enters
/// app code from a non-init code path -- much worse than
/// a clean fault.  See task #30 for the original V3.x
/// chain-probe finding.  Callers that need V3.x-app-on-V2.3-
/// seed must use a 3-core factory like `from_v171_v32`
/// (which performs the merge via `build_seeded_main_flash`).
/// Codex review of ec0381a (LOW), tightened by review of
/// 2983ff8 (LOW: "fault" was inaccurate).
fn build_v17_chain_single_main(
    control_hex_path: PathBuf,
    main_hex_path: PathBuf,
) -> Result<V17SingleMainHandle, String> {
    let control_hex = HexImage::from_hex_path(&control_hex_path)
        .map_err(|e| format!("control hex parse ({:?}): {e:?}", control_hex_path))?;
    let main_hex = HexImage::from_hex_path(&main_hex_path)
        .map_err(|e| format!("main hex parse ({:?}): {e:?}", main_hex_path))?;

    let control = build_v171_control_core(&control_hex);
    let mut main = build_stock_v23_main_core(&main_hex);
    main.peripherals.adc.set_an0_sample(0x0300);

    let mut chain = RustChain::new();
    let i_ctl = chain.push_core(control);
    let i_main = chain.push_core(main);

    chain.couple_uart(i_ctl, default_tx_pin(), i_main, default_rx_pin());
    chain.couple_uart(i_main, default_tx_pin(), i_ctl, default_rx_pin());

    let i_dsp = chain.push_tas3108(Tas3108::default());
    chain.couple_tas3108(i_main, i_dsp);
    let i_src = chain.push_src4382(Src4382::default());
    chain.couple_src4382(i_main, i_src);

    let i_lcd = chain.push_lcd(Hd44780::new());
    chain.couple_lcd(i_ctl, i_lcd);

    chain.apply_reset_all(ResetSource::PowerOn);
    chain.schedule_initial_steps(&[0, 0]);

    // Seed buttons-released AFTER POR (which wipes SFRs).
    // Mirrors `multicore_parity.rs::chain_v16b_v23_stock_
    // reaches_volume_screen` and the V1.71+V3.1 LCD parity
    // test seed.  Use the GPIO API rather than raw PORT writes
    // so the external level survives TRIS/ANSEL refreshes.
    release_control_buttons(&mut chain, i_ctl);

    Ok(V17SingleMainHandle {
        chain,
        i_ctl,
        i_main,
        i_lcd,
        i_dsp,
    })
}

/// Build a 1-core CONTROL-only chain (no MAIN, no UART
/// couplings, no DSP/SRC4382).  Mirror of gpsim's
/// `GpsimControlHarness` (`src/dlcp_fw/sim/control_gpsim.py`)
/// when invoked WITHOUT a synthetic-heartbeat pump -- a single
/// K20 core with an HD44780 LCD slave on the LCD-control pins,
/// driven by direct register pokes.  Used by V1.7 / V1.71
/// relocation-safety parity tests that boot CONTROL alone (no
/// MAIN heartbeats) and assert that stock V1.6b / rebuilt V1.7
/// / shifted V1.7 advance identical Tcy and emit identical
/// UART TX byte sequences.
///
/// `control_hex_path` accepts any K20 hex (V1.6b stock, V1.7
/// byte-identical rebuild, V1.7 shifted, V1.71).
///
/// The chain has NO MAIN core.  The pyclass `Chain` collapses
/// `i_main0 == i_main1 == i_ctl` so legacy main-targeting
/// methods don't crash if accidentally invoked, but
/// `inject_main_frames_fifo` and `read_dsp_reg` are not
/// meaningful in this topology.  Without a UART coupling,
/// `Chain::drain_completed_tx_bytes` falls through to its
/// loopback-sentinel branch and records every CONTROL TX byte
/// to `uart_tx_history` with `src_core == dst_core == i_ctl`,
/// so `tx_frames()` reports CONTROL's USART output even
/// without a peer (matching MAIN-only chain semantics).
fn build_v17_control_only_chain(control_hex_path: PathBuf) -> Result<V17SingleMainHandle, String> {
    let control_hex = HexImage::from_hex_path(&control_hex_path)
        .map_err(|e| format!("control hex parse ({:?}): {e:?}", control_hex_path))?;

    let control = build_v171_control_core(&control_hex);

    let mut chain = RustChain::new();
    let i_ctl = chain.push_core(control);

    let i_lcd = chain.push_lcd(Hd44780::new());
    chain.couple_lcd(i_ctl, i_lcd);

    chain.apply_reset_all(ResetSource::PowerOn);
    chain.schedule_initial_steps(&[0]);

    // Seed buttons-released AFTER POR (which wipes SFRs).
    // Mirrors the seeding pattern in
    // `build_v17_chain_single_main` so a V1.7 boot under
    // `disable_standby_check=False` does not interpret the
    // wiped PORTA/PORTC as "buttons stuck pressed".
    release_control_buttons(&mut chain, i_ctl);

    Ok(V17SingleMainHandle {
        chain,
        // Collapse i_main0/i_main1 onto i_ctl so legacy main-
        // targeting methods don't crash if accidentally
        // invoked.  CONTROL-only callers should not call
        // inject_main_frames_fifo / read_dsp_reg / etc. --
        // those only have meaningful semantics in chains with
        // a real MAIN core.
        i_ctl,
        i_main: i_ctl,
        i_lcd,
        i_dsp: 0, // placeholder; no DSP slave attached
    })
}

/// Build a 1-core MAIN-only chain (no CONTROL, no UART
/// couplings, no LCD).  Mirror of gpsim's `MainChainHarness`
/// (`src/dlcp_fw/sim/chain_gpsim.py:254`) -- a single 2455
/// core driven by direct register pokes and synthetic
/// chain-frame injection into the firmware's RX ring at
/// physical 0x0200..0x02BF (V3.x native_ring layout, depth
/// `MAIN_NATIVE_RX_SIZE = 192` bytes; rd index at 0x0C6,
/// wr index at 0x0C7).  Used by V3.1 / V3.2 MAIN-only
/// command-matrix / DSP-boot / I²C-fault tests that don't
/// need a real CONTROL peer.
///
/// `v3x_main_hex_path` is a V3.x app-only hex
/// (firmware/patched/releases/DLCP_Firmware_V3.x.hex);
/// `v23_seed_hex_path` is the silicon-correct seed (defaults
/// to V2.3-combined when None).  TAS3108 DSP slave attached
/// to MAIN's MSSP I²C bus -- without it, V3.x's `dsp_ping`
/// spin-loops on `wait_bf_clear_loop`.  AN0 ADC = 0x0300
/// (mid-rail mains-detect "high"), matching the gpsim
/// harness's default `standby_mode="hold"` post-boot ADC.
///
/// The chain has NO CONTROL core.  The pyclass `Chain` collapses
/// `i_ctl == i_main` so existing methods (`read_reg`,
/// `write_reg`, `step`, etc.) target the MAIN core.  An empty
/// HD44780 slave is pushed at `i_lcd = 0` so `lcd_lines()`
/// returns the 16-space default (LCD is unused on MAIN-only).
fn build_v3x_main_only_chain(
    v3x_main_hex_path: PathBuf,
    v23_seed_hex_path: PathBuf,
) -> Result<V17SingleMainHandle, String> {
    let v3x = HexImage::from_hex_path(&v3x_main_hex_path)
        .map_err(|e| format!("V3.x main hex parse ({:?}): {e:?}", v3x_main_hex_path))?;
    let v23_seed = HexImage::from_hex_path(&v23_seed_hex_path)
        .map_err(|e| format!("V2.3 seed hex parse ({:?}): {e:?}", v23_seed_hex_path))?;

    let mut main = build_seeded_main_core(&v3x, &v23_seed);
    main.peripherals.adc.set_an0_sample(0x0300);

    let mut chain = RustChain::new();
    let i_main = chain.push_core(main);

    let i_dsp = chain.push_tas3108(Tas3108::default());
    chain.couple_tas3108(i_main, i_dsp);
    let i_src = chain.push_src4382(Src4382::default());
    chain.couple_src4382(i_main, i_src);

    // Push a placeholder HD44780 -- never written to (no LCD
    // coupling), so `lcd_lines()` returns the 16-space default.
    // Lets MAIN-only callers reuse the existing `lcd_lines()`
    // method without crashing on an empty Vec; tests for
    // MAIN-only mode don't read LCD.
    let i_lcd = chain.push_lcd(Hd44780::new());

    chain.apply_reset_all(ResetSource::PowerOn);
    chain.schedule_initial_steps(&[0]);

    Ok(V17SingleMainHandle {
        chain,
        // Collapse i_ctl == i_main: every chain pyclass method
        // routes through `i_ctl`, and there's no CONTROL core
        // in MAIN-only mode.  read_reg / write_reg etc. then
        // target MAIN's data memory.
        i_ctl: i_main,
        i_main,
        i_lcd,
        i_dsp,
    })
}

/// Build a 2-core single-MAIN chain with a V3.x-app-on-V2.3-
/// seed MAIN (silicon-correct boot + V3.x app code).  Mirror
/// of `build_v17_chain_single_main` but with the V3.x app /
/// V2.3 seed merge MAIN core (`build_seeded_main_core`)
/// instead of a full-silicon MAIN copy.  Used by the V1.71
/// + V3.1 / V3.2 single-MAIN factories.
fn build_v17_v3x_chain_single_main(
    control_hex_path: PathBuf,
    v3x_main_hex_path: PathBuf,
    v23_seed_hex_path: PathBuf,
) -> Result<V17SingleMainHandle, String> {
    let control_hex = HexImage::from_hex_path(&control_hex_path)
        .map_err(|e| format!("control hex parse ({:?}): {e:?}", control_hex_path))?;
    let v3x = HexImage::from_hex_path(&v3x_main_hex_path)
        .map_err(|e| format!("V3.x main hex parse ({:?}): {e:?}", v3x_main_hex_path))?;
    let v23_seed = HexImage::from_hex_path(&v23_seed_hex_path)
        .map_err(|e| format!("V2.3 seed hex parse ({:?}): {e:?}", v23_seed_hex_path))?;

    let control = build_v171_control_core(&control_hex);
    let mut main = build_seeded_main_core(&v3x, &v23_seed);
    main.peripherals.adc.set_an0_sample(0x0300);

    let mut chain = RustChain::new();
    let i_ctl = chain.push_core(control);
    let i_main = chain.push_core(main);

    chain.couple_uart(i_ctl, default_tx_pin(), i_main, default_rx_pin());
    chain.couple_uart(i_main, default_tx_pin(), i_ctl, default_rx_pin());

    let i_dsp = chain.push_tas3108(Tas3108::default());
    chain.couple_tas3108(i_main, i_dsp);
    let i_src = chain.push_src4382(Src4382::default());
    chain.couple_src4382(i_main, i_src);

    let i_lcd = chain.push_lcd(Hd44780::new());
    chain.couple_lcd(i_ctl, i_lcd);

    chain.apply_reset_all(ResetSource::PowerOn);
    chain.schedule_initial_steps(&[0, 0]);

    release_control_buttons(&mut chain, i_ctl);

    Ok(V17SingleMainHandle {
        chain,
        i_ctl,
        i_main,
        i_lcd,
        i_dsp,
    })
}

fn build_v171_v32_chain(
    control_hex_path: PathBuf,
    main_hex_path: PathBuf,
    v23_seed_hex_path: PathBuf,
) -> Result<V171V32ChainHandle, String> {
    let v171 = HexImage::from_hex_path(&control_hex_path)
        .map_err(|e| format!("V1.71 hex parse ({:?}): {e:?}", control_hex_path))?;
    let v32 = HexImage::from_hex_path(&main_hex_path)
        .map_err(|e| format!("V3.2 hex parse ({:?}): {e:?}", main_hex_path))?;
    let v23 = HexImage::from_hex_path(&v23_seed_hex_path)
        .map_err(|e| format!("V2.3-combined hex parse ({:?}): {e:?}", v23_seed_hex_path))?;

    let control = build_v171_control_core(&v171);
    let mut main0 = build_seeded_main_core(&v32, &v23);
    main0.peripherals.adc.set_an0_sample(0x0300);
    let mut main1 = build_seeded_main_core(&v32, &v23);
    main1.peripherals.adc.set_an0_sample(0x0300);

    let mut chain = RustChain::new();
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
    let i_src0 = chain.push_src4382(Src4382::default());
    let i_src1 = chain.push_src4382(Src4382::default());
    chain.couple_src4382(i_main0, i_src0);
    chain.couple_src4382(i_main1, i_src1);

    let i_lcd = chain.push_lcd(Hd44780::new());
    chain.couple_lcd(i_ctl, i_lcd);

    chain.apply_reset_all(ResetSource::PowerOn);
    chain.schedule_initial_steps(&[0, 0, 0]);

    // Seed CONTROL buttons-released (active-low) AFTER POR.
    // POR wipes SFRs to 0x00 which V1.71 firmware interprets as
    // "every button stuck pressed" -- including STBY -- causing
    // CONTROL to enter standby screen (Zzz...) before the chain
    // can boot to DISPLAY mode.  Mirror of the seeding in
    // build_v17_chain_single_main (lines ~254-259) and
    // build_v17_control_only_chain (lines ~316-321).  Codex
    // hypothesis #1 from the V1.71+V3.2+V3.2 Zzz investigation
    // (2026-05-02): PORTA/PORTC=0x00 reads as buttons-pressed,
    // V1.71 sees STBY held -> renders Zzz instead of Volume.
    // Use the GPIO API rather than raw PORT writes so the
    // external released level survives TRIS/ANSEL refreshes.
    release_control_buttons(&mut chain, i_ctl);

    Ok(V171V32ChainHandle {
        chain,
        i_ctl,
        i_main0,
        i_main1,
        i_lcd,
        i_dsp0,
        i_dsp1,
    })
}

/// Python-visible Chain: thin wrapper over
/// `dlcp_sim::chain::Chain` plus the bookkeeping indices
/// each factory populated (so methods like `lcd_lines()`
/// know which LCD slave to read from).
///
/// `i_main0` / `i_main1` are 3-core-specific (`from_v171_v32`):
/// for single-MAIN topologies (`from_v16b_v23`,
/// `from_v17_chain`) both fields collapse to the single
/// MAIN's index.  Callers that care about the distinction
/// should not call `main1` for single-MAIN chains; the
/// migration tests don't yet read those getters.
#[pyclass]
struct Chain {
    inner: RustChain,
    i_ctl: usize,
    i_main0: usize,
    i_main1: usize,
    i_lcd: usize,
    /// MAIN0-side TX-record capture point.  Counts the number
    /// of `uart_tx_history` entries whose `src_core == i_main0`
    /// at the time of the last `tx_record_since_last_capture()`
    /// call (or 0 at construction).  The next call returns
    /// only entries pushed AFTER this point and advances the
    /// pointer to the new total.  See
    /// `tx_record_since_last_capture` for the mirror-of-gpsim
    /// semantics.
    tx_capture_main0: u64,
    /// MAIN1-side TX-record capture point.  Symmetric to
    /// `tx_capture_main0` but filters entries whose
    /// `src_core == i_main1`.  Used by 3-core wire-chain probes
    /// (CTL.tx -> MAIN0.rx -> MAIN1.rx -> CTL.rx) that need to
    /// distinguish "MAIN1 forwarded" from "CONTROL RX accepted"
    /// when localizing where bytes drop on the upstream return
    /// path.  Single-MAIN chains alias `i_main1 == i_main0`, so
    /// this capture coincides with `tx_capture_main0` and offers
    /// no new information there.  See task #94 probe.
    tx_capture_main1: u64,
    /// CONTROL-side RX capture point.  Symmetric to
    /// `tx_capture_ctl` but indexes the new
    /// `Chain::uart_rx_history` (FIFO-accepted bytes) filtered
    /// by `r.dst_core == self.i_ctl`.  Used by task #94 probes
    /// to compare wire-attempts (`uart_tx_history`) vs
    /// silicon-accepted bytes (`uart_rx_history`) and localize
    /// byte loss between MAIN1's TX and CONTROL's silicon RX
    /// FIFO.  See `mark_ctl_rx_capture_point` /
    /// `ctl_rx_record_since_last_capture`.
    rx_capture_ctl: u64,
    /// MAIN0-side RX capture point.  Same shape as
    /// `rx_capture_ctl` but filters by
    /// `r.dst_core == self.i_main0`.  Useful for verifying
    /// MAIN0's RX accepts the bytes CONTROL sends downstream.
    rx_capture_main0: u64,
    /// MAIN1-side RX capture point.  Same shape but filters
    /// by `r.dst_core == self.i_main1`.  Useful for verifying
    /// MAIN1's RX accepts the bytes MAIN0 forwards (and any
    /// CONTROL bytes that hop through MAIN0's parser
    /// decrement-and-forward path).
    rx_capture_main1: u64,
    /// CONTROL-side TX-record capture point.  Symmetric to
    /// `tx_capture_main0` but filters entries whose
    /// `src_core == i_ctl`.  Used by tests that need to bound
    /// TX observation to a specific firmware-PC window (e.g.
    /// "frames emitted between the IR injection and the next
    /// function_028 entry") via
    /// `mark_ctl_tx_capture_point` + `ctl_tx_record_since_last_
    /// capture` + `step_until_pc_hit(core_idx=0, ...)`.
    tx_capture_ctl: u64,
    /// When true, `step()` applies the per-step "force
    /// CONNECTED" hook to CONTROL: ORs bits 1+3 into 0x01F
    /// (CONNECTED + event-exit) and resets the idle timer at
    /// 0x09D/0x09E.  Mirror of gpsim's
    /// `GpsimControlHarness(heartbeat_force_connected=True)`
    /// behavior.  Used by CONTROL-only chains that must keep
    /// the firmware in DISPLAY mode without a real MAIN peer.
    ///
    /// `warmup_force_connected()` ALSO honours this flag for
    /// post-warmup `step()` calls, but during warmup itself
    /// the hook is gated on a local `display_entered` flag
    /// (mirror of gpsim's `_heartbeat_active` gate around
    /// `_heartbeat_pre_step`): the hook is NOT applied
    /// pre-DISPLAY so the firmware's natural bit1 transition
    /// stays observable; once observed, the hook starts firing
    /// each chunk.  See `warmup_force_connected` for the full
    /// flow.
    ///
    /// Default false; enable via `enable_force_connected()` or
    /// implicitly via `warmup_force_connected()`.
    force_connected: bool,
}

/// Default `step()` advance = 200_000 Tcy.  This is just a
/// convenience cadence for tests that don't care about the
/// exact amount; it happens to match gpsim's
/// `SingleMainChainHarness` `chunk_cycles=200_000` default,
/// so tests previously written for gpsim that call
/// `h.step()` repeatedly run the same per-step Tcy here.
/// The rust simulator's universal-clock scheduler makes the
/// notion of "chunks" obsolete -- this is a fixed
/// convenience constant, NOT a configurable per-instance
/// cadence (gpsim's chunked-alternating execution is a
/// serialization artifact we deliberately do NOT replicate
/// here; see `step_tcy` for explicit advancement when a
/// test needs a specific amount).
const DEFAULT_STEP_TCY: u64 = 200_000;
/// K20 universal ticks per Tcy (Fosc 12 MHz, Tcy = 4/Fosc,
/// universal clock 48 MHz -> 48 / 3 = 16 ticks/Tcy).  See
/// `crates/dlcp-sim/src/chain.rs:17` for the universal-
/// clock derivation.  Mirror of
/// `peripherals::osc::ticks_per_tcy(Variant::Pic18F25K20)`.
const TICKS_PER_TCY_K20: u64 = 16;
/// PIC18F2455 universal ticks per Tcy (Fosc 16 MHz, Tcy =
/// 4/Fosc, universal clock 48 MHz -> 48 / 4 = 12 ticks/Tcy).
/// Mirror of
/// `peripherals::osc::ticks_per_tcy(Variant::Pic18F2455)`.
/// Used by `step_tcy` for MAIN-only chains where `tcy`
/// is interpreted as PIC18F2455 instruction cycles
/// (matching gpsim's MainChainHarness `chunk_cycles=N`
/// constructor knob).
const TICKS_PER_TCY_2455: u64 = 12;

/// Match the gpsim harness's WAITING screen heuristic
/// (`chain_gpsim.py::_is_waiting_lcd`): the substring
/// "WAITING FOR DLCP" (case-insensitive) appears on
/// either line of the HD44780 display.  Kept centralised
/// so any future tightening of the gpsim heuristic flows
/// to the rust facade in one place.
fn lcd_is_waiting(line1: &str, line2: &str) -> bool {
    let l1 = line1.to_uppercase();
    let l2 = line2.to_uppercase();
    l1.contains("WAITING FOR DLCP") || l2.contains("WAITING FOR DLCP")
}

/// V1.6b / V1.71 panel-button keymap: which active-low
/// PORTx bit each panel button is wired to.  Per the V1.71
/// source `dlcp_control_v171.asm:1968+` ("0x027.bit0 = RA3
/// (Standby) ... active LOW"), the firmware treats logic-
/// LOW on these pins as "button pressed".  Names match
/// gpsim's `GpsimControlHarness.press` keys so dual-mode
/// callers can pass identical strings.
fn panel_button_pin(key: &str) -> Result<(PortLetter, u8), String> {
    let canonical = key.trim().to_ascii_uppercase();
    match canonical.as_str() {
        "SELECT" => Ok((PortLetter::A, 1)),
        "DOWN" => Ok((PortLetter::A, 2)),
        "STBY" => Ok((PortLetter::A, 3)),
        "RIGHT" => Ok((PortLetter::A, 4)),
        "UP" => Ok((PortLetter::C, 0)),
        "LEFT" => Ok((PortLetter::C, 5)),
        _ => Err(format!(
            "unknown panel button {key:?}; expected one of \
             SELECT, DOWN, STBY, RIGHT, UP, LEFT"
        )),
    }
}

fn parse_port_letter(name: &str) -> Result<PortLetter, String> {
    match name.trim().to_ascii_uppercase().as_str() {
        "A" => Ok(PortLetter::A),
        "B" => Ok(PortLetter::B),
        "C" => Ok(PortLetter::C),
        other => Err(format!(
            "unknown PORT name {other:?}; expected one of A, B, C"
        )),
    }
}

/// Universal-tick budget for a button press: hold the bit
/// LOW for `BUTTON_HOLD_TICKS`, then release HIGH and
/// step `BUTTON_RELEASE_SETTLE_TICKS` more.  V1.71's
/// `button_scan_debounce` requires the press to be stable
/// across 4 button-scan polls (`asm:1965 "4-tick stability
/// counter at 0x0BB"`).  At the K20's ~2.5 ms button-scan
/// interval, holding for 50 M ticks (~3 M Tcy ≈ 1 sec sim
/// at 48 MHz universal) gives ~400 polls of headroom -- far
/// more than the firmware needs and safely past the
/// debounce threshold.  Mirrors the V1.71+V3.2 STDBY-
/// button test in
/// `crates/dlcp-sim/tests/multicore_parity.rs:3736-3739`.
const BUTTON_HOLD_TICKS: u64 = 50_000_000;
const BUTTON_RELEASE_SETTLE_TICKS: u64 = 50_000_000;

impl Chain {
    /// Look up the index of the FIRST TAS3108 slave coupled
    /// to MAIN0 in `inner.tas3108_slaves`.  Used by methods
    /// that read or program DSP state (`read_dsp_reg`,
    /// `set_dsp_i2c_fault`, `clear_dsp_i2c_faults`).  Returns
    /// a Python-visible RuntimeError if no DSP slave is wired
    /// to MAIN0 (e.g. a chain built without
    /// `couple_tas3108`).
    fn dsp_slave_index(&self) -> PyResult<usize> {
        self.inner
            .tas3108_couplings
            .iter()
            .find(|(master, _)| *master == self.i_main0)
            .map(|(_, slave)| *slave)
            .ok_or_else(|| {
                pyo3::exceptions::PyRuntimeError::new_err(
                    "no TAS3108 slave coupled to MAIN0 -- chain was \
                     not built with a DSP slave",
                )
            })
    }

    /// Universal-clock ticks per Tcy for the core at `i_ctl`.
    /// K20 chains (mixed CONTROL+MAIN where K20 is the primary
    /// timekeeper, OR CONTROL-only chains where K20 is the only
    /// core) advance at 16 ticks/Tcy; PIC18F2455 chains
    /// (MAIN-only, where MAIN is collapsed onto i_ctl) advance
    /// at 12 ticks/Tcy.  Used by `step_tcy`, `step`, and
    /// `step_until_tx_quiescent` to convert a Tcy budget into a
    /// universal-tick budget.  The earlier `i_ctl == i_main0`
    /// collapse-detection heuristic (b828519 LOW) broke once
    /// `from_v17_control_only` collapsed those indices with a
    /// K20 core (codex MEDIUM from review of 933872b /
    /// follow-up of e7a72f3); switching to direct variant
    /// inspection covers all three topologies correctly.
    fn tcy_factor(&self) -> u64 {
        use dlcp_sim::memory::Variant;
        match self.inner.cores[self.i_ctl].variant() {
            Variant::Pic18F25K20 => TICKS_PER_TCY_K20,
            Variant::Pic18F2455 => TICKS_PER_TCY_2455,
        }
    }

    /// Apply the gpsim heartbeat-force-connected pre-step
    /// pokes to CONTROL's RAM (mirror of
    /// `control_gpsim.py::GpsimControlHarness._heartbeat_pre_step`
    /// for `heartbeat_force_connected=True`):
    ///   * 0x01F |= 0x0A    (bit3 = event-exit flag used by
    ///                       function_042; bit1 = CONNECTED)
    ///   * 0x09D = 0xFF     (idle-timeout LSB)
    ///   * 0x09E = 0xFF     (idle-timeout MSB)
    ///
    /// The first OR keeps the firmware in DISPLAY/CONNECTED
    /// mode without a real MAIN peer; the idle-timer reset
    /// prevents the firmware's local reconnect logic from
    /// clearing CONNECTED within a single chunk.
    fn apply_force_connected_hook(&mut self) {
        let mem = &mut self.inner.cores[self.i_ctl].memory;
        let cur = mem.read_raw(dlcp_sim::memory::Address::from_raw(0x01F));
        mem.write_raw(dlcp_sim::memory::Address::from_raw(0x01F), cur | 0x0A);
        mem.write_raw(dlcp_sim::memory::Address::from_raw(0x09D), 0xFF);
        mem.write_raw(dlcp_sim::memory::Address::from_raw(0x09E), 0xFF);
    }

    /// Inject `bytes` into CONTROL's RX ring buffer.  V1.6b /
    /// V1.71 ring layout: base = 0x066, depth = 0x30 (48 bytes),
    /// rd index at 0x098, wr index at 0x099.  Returns false if
    /// the ring would overflow (>= 0x2C bytes pending).  Mirror
    /// of `control_gpsim.py::_inject_rx_bytes`.
    fn inject_control_rx_bytes_inner(&mut self, bytes: &[u8]) -> bool {
        const RX_BASE: u16 = 0x066;
        const RX_DEPTH: u16 = 0x30;
        const RX_RD: u16 = 0x098;
        const RX_WR: u16 = 0x099;
        let mem = &mut self.inner.cores[self.i_ctl].memory;
        let rd = mem.read_raw(dlcp_sim::memory::Address::from_raw(RX_RD)) as u16 % RX_DEPTH;
        let mut wr = mem.read_raw(dlcp_sim::memory::Address::from_raw(RX_WR)) as u16 % RX_DEPTH;
        let used = (wr + RX_DEPTH - rd) % RX_DEPTH;
        if used > 0x2C {
            return false;
        }
        for &b in bytes {
            mem.write_raw(
                dlcp_sim::memory::Address::from_raw(RX_BASE + (wr % RX_DEPTH)),
                b,
            );
            wr = (wr + 1) % RX_DEPTH;
        }
        mem.write_raw(
            dlcp_sim::memory::Address::from_raw(RX_WR),
            (wr & 0xFF) as u8,
        );
        true
    }
}

#[pymethods]
impl Chain {
    /// Construct a 3-core ring (V1.71 CONTROL + V3.2
    /// MAIN0 + V3.2 MAIN1) with UART ring, DSP slaves,
    /// LCD slave, POR-reset and initial-step schedule
    /// applied.  Equivalent to the prelude of
    /// `multicore_parity.rs::three_core_ring_v171_v32_v32_*`.
    #[staticmethod]
    #[pyo3(signature = (
        control_hex_path=None,
        main_hex_path=None,
        v23_seed_hex_path=None,
    ))]
    fn from_v171_v32(
        control_hex_path: Option<String>,
        main_hex_path: Option<String>,
        v23_seed_hex_path: Option<String>,
    ) -> PyResult<Self> {
        // Default to canonical release paths; tests that build hexes
        // from current source into a tmp path can pass overrides so
        // both backends test the same byte-identical fixture (codex
        // task #77).
        let control = control_hex_path
            .map(PathBuf::from)
            .unwrap_or_else(v171_control_hex_path);
        let main = main_hex_path
            .map(PathBuf::from)
            .unwrap_or_else(v32_main_hex_path);
        let v23 = v23_seed_hex_path
            .map(PathBuf::from)
            .unwrap_or_else(v23_main_combined_hex_path);
        let handle = build_v171_v32_chain(control, main, v23)
            .map_err(|e| PyRuntimeError::new_err(format!("from_v171_v32: {e}")))?;
        Ok(Self {
            inner: handle.chain,
            i_ctl: handle.i_ctl,
            i_main0: handle.i_main0,
            i_main1: handle.i_main1,
            i_lcd: handle.i_lcd,
            tx_capture_main0: 0,
            tx_capture_main1: 0,
            rx_capture_ctl: 0,
            rx_capture_main0: 0,
            rx_capture_main1: 0,
            tx_capture_ctl: 0,
            force_connected: false,
        })
    }

    /// Convenience: stock V1.6b CONTROL + stock V2.3 MAIN
    /// single-MAIN chain.  Mirror of the Rust prereq test
    /// `multicore_parity.rs::chain_v16b_v23_stock_reaches_volume_screen`
    /// and the gpsim baseline
    /// `tests/sim/test_v17_chain.py::test_v17_stock_v16b_chain_reaches_display`.
    #[staticmethod]
    fn from_v16b_v23() -> PyResult<Self> {
        Self::from_v17_chain(v16b_control_hex_path().to_string_lossy().into_owned(), None)
    }

    /// Generic V1.7-family + V3.x single-MAIN factory.
    /// Accepts any K20 CONTROL hex (V1.71, V1.7-shifted,
    /// etc.) paired with a V3.x app-only MAIN hex (V3.1,
    /// V3.2 release, V3.x diagnostic build).  The V3.x
    /// app is merged onto a V2.3-combined seed
    /// (`build_seeded_main_core`) for silicon-correct
    /// boot.  Mirror of the chain-construction prelude in
    /// `crates/dlcp-sim/tests/multicore_parity.rs::
    /// chain_v171_v31_reaches_first_uart_tx` (modulo the
    /// 3-core ring topology -- this is a 2-core single-MAIN
    /// variant for `tests/sim/test_v171_v31_chain.py`).
    /// `v23_seed_hex_path=None` defaults to
    /// `firmware/stock/main/DLCP Firmware V2.3-combined.hex`.
    #[staticmethod]
    #[pyo3(signature = (control_hex_path, v3x_main_hex_path, v23_seed_hex_path=None))]
    fn from_v17_v3x_chain(
        control_hex_path: String,
        v3x_main_hex_path: String,
        v23_seed_hex_path: Option<String>,
    ) -> PyResult<Self> {
        let v23_seed = v23_seed_hex_path
            .map(PathBuf::from)
            .unwrap_or_else(v23_main_combined_hex_path);
        let handle = build_v17_v3x_chain_single_main(
            PathBuf::from(control_hex_path),
            PathBuf::from(v3x_main_hex_path),
            v23_seed,
        )
        .map_err(|e| PyRuntimeError::new_err(format!("from_v17_v3x_chain: {e}")))?;
        Ok(Self {
            inner: handle.chain,
            i_ctl: handle.i_ctl,
            i_main0: handle.i_main,
            i_main1: handle.i_main,
            i_lcd: handle.i_lcd,
            tx_capture_main0: 0,
            tx_capture_main1: 0,
            rx_capture_ctl: 0,
            rx_capture_main0: 0,
            rx_capture_main1: 0,
            tx_capture_ctl: 0,
            force_connected: false,
        })
    }

    /// Convenience: V1.71 CONTROL + V3.1 MAIN single-MAIN
    /// chain.  Uses the canonical V3.1 release hex (app-only)
    /// merged onto V2.3-combined.
    #[staticmethod]
    fn from_v171_v31() -> PyResult<Self> {
        Self::from_v17_v3x_chain(
            repo_root()
                .join("firmware/patched/releases/DLCP_Control_V1.71.hex")
                .to_string_lossy()
                .into_owned(),
            v31_main_hex_path().to_string_lossy().into_owned(),
            None,
        )
    }

    /// MAIN-only single-core factory.  Mirror of gpsim's
    /// `MainChainHarness(main_hex, transport_mode="native_ring")`
    /// (see `chain_gpsim.py:254`).  Builds a single 2455
    /// core with V3.x app + V2.3-combined seed merge,
    /// TAS3108 DSP slave on MSSP I²C, AN0 ADC = 0x0300,
    /// no CONTROL.  All other Chain methods (`read_reg`,
    /// `write_reg`, `step`, ...) target the MAIN core
    /// because internally `i_ctl == i_main` for MAIN-only
    /// chains.  Use `inject_main_frames_fifo` to inject
    /// synthetic chain frames into MAIN's RX ring.
    /// `v23_seed_hex_path` defaults to V2.3-combined.
    #[staticmethod]
    #[pyo3(signature = (v3x_main_hex_path, v23_seed_hex_path=None))]
    fn from_v3x_main_only(
        v3x_main_hex_path: String,
        v23_seed_hex_path: Option<String>,
    ) -> PyResult<Self> {
        let v23_seed = v23_seed_hex_path
            .map(PathBuf::from)
            .unwrap_or_else(v23_main_combined_hex_path);
        let handle = build_v3x_main_only_chain(PathBuf::from(v3x_main_hex_path), v23_seed)
            .map_err(|e| PyRuntimeError::new_err(format!("from_v3x_main_only: {e}")))?;
        Ok(Self {
            inner: handle.chain,
            i_ctl: handle.i_ctl,
            i_main0: handle.i_main,
            i_main1: handle.i_main,
            i_lcd: handle.i_lcd,
            tx_capture_main0: 0,
            tx_capture_main1: 0,
            rx_capture_ctl: 0,
            rx_capture_main0: 0,
            rx_capture_main1: 0,
            tx_capture_ctl: 0,
            force_connected: false,
        })
    }

    /// Convenience: V3.1 MAIN-only chain (canonical V3.1
    /// release hex + V2.3-combined seed).
    #[staticmethod]
    fn from_v31_main_only() -> PyResult<Self> {
        Self::from_v3x_main_only(v31_main_hex_path().to_string_lossy().into_owned(), None)
    }

    /// Convenience: V3.2 MAIN-only chain (canonical V3.2
    /// release hex + V2.3-combined seed).
    #[staticmethod]
    fn from_v32_main_only() -> PyResult<Self> {
        Self::from_v3x_main_only(v32_main_hex_path().to_string_lossy().into_owned(), None)
    }

    /// Generic V1.7-family single-MAIN factory.  Accepts
    /// any K20 CONTROL hex (V1.6b stock, V1.7 byte-identical
    /// rebuild, V1.7 shifted, V1.71) paired with a
    /// FULL-SILICON 2455 MAIN hex (defaults to V2.3-combined
    /// when `main_hex_path` is None).  No flash merge:
    /// stock V2.3-combined is silicon-correct as-is, and
    /// the V1.7 / V1.71 CONTROL rebuild source is byte-
    /// identical to V1.6b stock (the V1.7 source rewrite
    /// was designed to produce identical hex; see
    /// `test_v17_equivalence.py`).  V3.x app-only MAIN hexes
    /// won't work -- they leave `[0x0000, 0x1000)` erased,
    /// and the executor walks the erased reset window as
    /// NOPs before re-entering app code from the wrong path
    /// (see `build_v17_chain_single_main` for the full
    /// rationale).  Use a 3-core factory like `from_v171_v32`
    /// for V3.x.  Mirror of
    /// `multicore_parity.rs::chain_v16b_v23_stock_reaches_volume_screen`'s
    /// chain-construction prelude.
    #[staticmethod]
    #[pyo3(signature = (control_hex_path, main_hex_path=None))]
    fn from_v17_chain(control_hex_path: String, main_hex_path: Option<String>) -> PyResult<Self> {
        let main_path = main_hex_path
            .map(PathBuf::from)
            .unwrap_or_else(v23_main_combined_hex_path);
        let handle = build_v17_chain_single_main(PathBuf::from(control_hex_path), main_path)
            .map_err(|e| PyRuntimeError::new_err(format!("from_v17_chain: {e}")))?;
        Ok(Self {
            inner: handle.chain,
            i_ctl: handle.i_ctl,
            // Single-MAIN: both legacy main0/main1 getters
            // collapse to the single MAIN's index.  See the
            // pyclass docstring above for rationale.
            i_main0: handle.i_main,
            i_main1: handle.i_main,
            i_lcd: handle.i_lcd,
            tx_capture_main0: 0,
            tx_capture_main1: 0,
            rx_capture_ctl: 0,
            rx_capture_main0: 0,
            rx_capture_main1: 0,
            tx_capture_ctl: 0,
            force_connected: false,
        })
    }

    /// CONTROL-only single-K20 chain: 1 K20 core + HD44780
    /// LCD slave, no MAIN, no UART couplings, no DSP / SRC4382.
    /// Mirror of gpsim's `GpsimControlHarness(hex,
    /// fast_boot=False)` invocation without a synthetic-
    /// heartbeat pump.
    ///
    /// Used by V1.7 / V1.71 relocation-safety tests that boot
    /// CONTROL alone (no MAIN heartbeats) and assert that
    /// stock V1.6b, rebuilt V1.7, and shifted V1.7 advance
    /// identical Tcy and emit identical UART TX byte sequences.
    /// `current_cycle` and `tx_frames()` work without changes
    /// (TX bytes are captured via the `drain_completed_tx_bytes`
    /// loopback-sentinel branch -- the same mechanism that
    /// makes MAIN-only chains observable).
    ///
    /// Methods that require a MAIN core (`inject_main_frames_
    /// fifo`, `read_dsp_reg`, `set_dsp_i2c_fault`, etc.) will
    /// silently target CONTROL or raise RuntimeError -- callers
    /// must not invoke them on this topology.
    #[staticmethod]
    fn from_v17_control_only(control_hex_path: String) -> PyResult<Self> {
        let handle = build_v17_control_only_chain(PathBuf::from(control_hex_path))
            .map_err(|e| PyRuntimeError::new_err(format!("from_v17_control_only: {e}")))?;
        Ok(Self {
            inner: handle.chain,
            i_ctl: handle.i_ctl,
            // Collapse main0/main1 onto i_ctl: the chain has
            // no MAIN core, so legacy main-targeting getters
            // return CONTROL's index.  Methods that semantically
            // need a MAIN (DSP regs, frame injection) are not
            // meaningful in this topology.
            i_main0: handle.i_main,
            i_main1: handle.i_main,
            i_lcd: handle.i_lcd,
            tx_capture_main0: 0,
            tx_capture_main1: 0,
            rx_capture_ctl: 0,
            rx_capture_main0: 0,
            rx_capture_main1: 0,
            tx_capture_ctl: 0,
            force_connected: false,
        })
    }

    /// Advance the universal clock by `tcy` instruction
    /// cycles.  The Tcy unit is interpreted by inspecting the
    /// variant of the core at `i_ctl`: K20 chains (mixed
    /// CONTROL+MAIN where K20 is the primary timekeeper, or
    /// CONTROL-only chains where K20 is the only core) advance
    /// at 16 ticks/Tcy; 2455 chains (MAIN-only chains where
    /// MAIN is collapsed onto i_ctl) advance at 12 ticks/Tcy.
    /// See `tcy_factor` for the helper, and codex review of
    /// 933872b / b828519 for the rationale (the earlier
    /// `i_ctl == i_main0` collapse-detection heuristic broke
    /// once `from_v17_control_only` also collapsed those
    /// indices with a K20 core).  Universal-clock derivation:
    /// `crates/dlcp-sim/src/chain.rs:17` (48 MHz universal
    /// clock; K20 Fosc=12 MHz so Tcy=4/12 MHz=333 ns; 2455
    /// Fosc=16 MHz so Tcy=4/16 MHz=250 ns).
    ///
    /// Use this when a test needs a specific amount of
    /// simulated time -- e.g. parity tests that previously
    /// relied on gpsim's per-harness `chunk_cycles` should
    /// say `chain.step_tcy(600_000)` explicitly rather than
    /// expect a configurable chunk size.  The rust
    /// simulator's universal-clock scheduler runs both
    /// cores in lock-step at instruction-level granularity;
    /// gpsim's chunked-alternating execution is a
    /// serialization artifact we deliberately do NOT
    /// replicate.
    fn step_tcy(&mut self, tcy: u64) {
        self.inner.step_ticks(tcy * self.tcy_factor());
    }

    /// Advance the universal clock by `n_ticks` and dispatch
    /// every event whose deadline `<=` the new tick.  Direct
    /// passthrough to `Chain::step_ticks`.
    fn step_ticks(&mut self, n_ticks: u64) {
        self.inner.step_ticks(n_ticks);
    }

    /// Current universal-clock tick.
    fn current_tick(&self) -> u64 {
        self.inner.current_tick
    }

    /// Index of the CONTROL core in the chain.
    #[getter]
    fn ctl(&self) -> usize {
        self.i_ctl
    }

    /// Index of MAIN0.  For single-MAIN topologies this
    /// returns the same index as `main1`.
    #[getter]
    fn main0(&self) -> usize {
        self.i_main0
    }

    /// Index of MAIN1.  For single-MAIN topologies this
    /// returns the same index as `main0`.
    #[getter]
    fn main1(&self) -> usize {
        self.i_main1
    }

    /// Count of `uart_tx_history` records dropped from the
    /// front since chain construction or the last
    /// `apply_reset_all` (e.g. via the rust-side
    /// `Chain::apply_reset_all`).  Use this to detect that
    /// `tx_record_since_last_capture` (and its mirror
    /// helpers) returned a truncated tail because the
    /// rolling-window cap evicted older matching records
    /// since the last mark -- the absolute-counter delta
    /// asks for more bytes than the buffer can deliver.
    /// Codex MEDIUM from review of feb091e: capture
    /// helpers return only `Vec<u8>`, so without this
    /// accessor Python callers cannot distinguish "exactly
    /// N bytes arrived" from "many more bytes arrived but
    /// were truncated".  Mark + capture pattern with loss
    /// detection:
    ///
    ///     pre = chain.uart_tx_history_dropped
    ///     chain.mark_tx_capture_point()
    ///     chain.step_tcy(...)
    ///     bytes = chain.tx_record_since_last_capture()
    ///     if chain.uart_tx_history_dropped > pre:
    ///         # rolling window evicted some bytes between
    ///         # mark and capture; bytes is the surviving
    ///         # tail, not the full set.
    #[getter]
    fn uart_tx_history_dropped(&self) -> u64 {
        self.inner.uart_tx_history_dropped
    }

    /// Mirror of `uart_tx_history_dropped` for the
    /// destination-accept-side `uart_rx_history` buffer.
    /// Same loss-detection pattern applies to
    /// `ctl_rx_record_since_last_capture` /
    /// `main0_rx_record_since_last_capture` /
    /// `main1_rx_record_since_last_capture`.
    #[getter]
    fn uart_rx_history_dropped(&self) -> u64 {
        self.inner.uart_rx_history_dropped
    }

    /// Snapshot of the HD44780 LCD's two display lines as
    /// a `(line1, line2)` tuple of UTF-8-lossy strings.
    /// Trailing whitespace is preserved (callers decide
    /// whether to trim).  Returns the EMPTY-DDRAM default
    /// (16 spaces each) on a freshly-reset chain.
    fn lcd_lines(&self) -> (String, String) {
        let lcd = &self.inner.lcd_slaves[self.i_lcd];
        (lcd.line1(), lcd.line2())
    }

    /// True when CONTROL has marked itself as connected to
    /// the chain ring.  Reads bit 1 of physical RAM 0x01F
    /// on the CONTROL core (the `control_flags` byte the
    /// V1.6b / V1.71 firmware uses to record handshake
    /// state).  Mirror of
    /// `chain_gpsim.py::SingleMainChainHarness::is_connected`.
    fn is_connected(&self) -> bool {
        let flags = self.inner.cores[self.i_ctl]
            .memory
            .read_raw(dlcp_sim::memory::Address::from_raw(0x01F));
        (flags & 0x02) != 0
    }

    /// True when CONTROL's LCD shows the WAITING screen on
    /// either row.  Mirror of
    /// `chain_gpsim.py::_is_waiting_lcd`.
    fn is_waiting(&self) -> bool {
        let lcd = &self.inner.lcd_slaves[self.i_lcd];
        lcd_is_waiting(&lcd.line1(), &lcd.line2())
    }

    /// Step the chain in `DEFAULT_STEP_TCY`-Tcy chunks (200K
    /// Tcy = 3.2 M universal ticks) up to `limit` chunks,
    /// returning early as soon as the chain has reached the
    /// steady-state CONNECTED Volume display.  Returns the
    /// number of chunks actually consumed (== `limit` if
    /// the predicate never fired).
    ///
    /// Predicate: `is_connected()` AND `!is_waiting()` AND
    /// LCD line 1 contains the substring `"Volume:"`.
    ///
    /// Why stricter than `chain_gpsim.py::SingleMainChainHarness::run_until_connected`:
    /// gpsim's predicate is just `is_connected AND !is_waiting`,
    /// and gpsim's chunk-stepping happens to align such that
    /// when the predicate first fires, the LCD already shows
    /// `Volume:` (an empirical coincidence -- the gpsim
    /// `_run_pair` test relies on `assert "Volume:" in last.lcd[0]`
    /// holding at that moment).  The Rust chain advances
    /// CONTROL and MAIN within the same universal-tick
    /// scheduler instead of gpsim's per-MAIN/per-CONTROL
    /// alternating chunks, so byte delivery is faster and
    /// `control_flags.CONNECTED` (bit 1 of 0x01F) can flip
    /// True on transient chain-frame parses (V1.7 source
    /// `dlcp_control_v17.asm:828` -- `bsf control_flags, 1`
    /// inside the cmd=0x03 / data=0x01 parser branch) before
    /// the LCD has rendered the Volume screen.  Tightening
    /// the predicate to also require `Volume:` aligns the
    /// Rust facade with the assertion the migrated test
    /// makes.  `is_connected()` and `is_waiting()` are still
    /// available as standalone getters for tests that need
    /// the gpsim-compatible flag-only check.
    fn run_until_connected(&mut self, limit: usize) -> usize {
        let step_ticks = DEFAULT_STEP_TCY * TICKS_PER_TCY_K20;
        for chunk in 0..limit {
            self.inner.step_ticks(step_ticks);
            if self.is_connected()
                && !self.is_waiting()
                && self.inner.lcd_slaves[self.i_lcd]
                    .line1()
                    .contains("Volume:")
            {
                return chunk + 1;
            }
        }
        limit
    }

    /// Step in `DEFAULT_STEP_TCY`-Tcy chunks (200K Tcy each)
    /// up to `limit` chunks, returning early as soon as
    /// `is_waiting()` is true.  Returns the number of
    /// chunks actually consumed (== `limit` if the
    /// predicate never fired).  Mirror of
    /// `chain_gpsim.py::SingleMainChainHarness::run_until_waiting`.
    /// Used by the V1.7 blackout/wake migration test to
    /// verify CONTROL falls back to the WAITING screen after
    /// a wake-while-blacked-out.
    fn run_until_waiting(&mut self, limit: usize) -> usize {
        let step_ticks = DEFAULT_STEP_TCY * TICKS_PER_TCY_K20;
        for chunk in 0..limit {
            self.inner.step_ticks(step_ticks);
            if self.is_waiting() {
                return chunk + 1;
            }
        }
        limit
    }

    /// Step the chain by `n_chunks` chunks of
    /// `DEFAULT_STEP_TCY * 16` ticks each (no early-exit
    /// predicate).  Mirror of
    /// `chain_gpsim.py::SingleMainChainHarness::step_many`.
    /// Used by the V1.7 blackout/wake migration test to
    /// give the firmware time to settle into standby (Zzz)
    /// after the STBY-press, before re-pressing to wake.
    fn step_many(&mut self, n_chunks: usize) {
        let step_ticks = DEFAULT_STEP_TCY * TICKS_PER_TCY_K20;
        for _ in 0..n_chunks {
            self.inner.step_ticks(step_ticks);
        }
    }

    /// Toggle the chain's UART-blackout flag (defaults to
    /// false at construction).  When enabled, every
    /// completed UART TX byte is dropped instead of
    /// delivered to wired destinations -- modelling a
    /// physical chain disconnect (CAT5 unplug, optocoupler
    /// fault).  Cores keep running and TX history is NOT
    /// updated for dropped bytes.  Mirror of
    /// `chain_gpsim.py::SingleMainChainHarness::set_blackout`
    /// modulo gpsim's `LinkPipe.clear` step (gpsim flushes
    /// in-flight bytes at the bridge layer; the rust
    /// engine's destination-side RCREG residual is bounded
    /// by the firmware's read latency, ~hundreds of Tcy).
    fn set_blackout(&mut self, enabled: bool) {
        self.inner.set_uart_blackout(enabled);
    }

    /// Inject a panel-button press on CONTROL.  Drives the
    /// button's active-low PORTx bit LOW, holds for
    /// `BUTTON_HOLD_TICKS` (50 M ticks ≈ 1 sec sim, well
    /// past V1.71's 4-poll debounce window), releases the
    /// bit HIGH, and steps `BUTTON_RELEASE_SETTLE_TICKS`
    /// more.  Mirror of
    /// `chain_gpsim.py::SingleMainChainHarness::press`.
    /// Accepted keys (case-insensitive): SELECT, DOWN,
    /// STBY, RIGHT, UP, LEFT.  Raises `ValueError` for
    /// any other key.  See `panel_button_pin` for the
    /// PORTx mapping rationale.
    fn press(&mut self, key: &str) -> PyResult<()> {
        let (port, bit) = panel_button_pin(key).map_err(PyValueError::new_err)?;
        self.inner.set_pin_low(self.i_ctl, port, bit);
        self.inner.step_ticks(BUTTON_HOLD_TICKS);
        self.inner.set_pin_high(self.i_ctl, port, bit);
        self.inner.step_ticks(BUTTON_RELEASE_SETTLE_TICKS);
        Ok(())
    }

    /// Read a single byte of CONTROL's data memory at the
    /// given physical address (e.g. 0x01F = control_flags,
    /// 0x0BF = display_state_index, 0x0B8 = input_select_
    /// cache, 0x0B9 = volume_cache).  Mirror of
    /// `control_gpsim.py::GpsimControlHarness.read_reg`.
    /// `addr` is interpreted as a raw 12-bit physical
    /// address; the caller is responsible for resolving
    /// any banking / Access-Bank translation.
    fn read_reg(&self, addr: u16) -> u8 {
        self.inner.cores[self.i_ctl]
            .memory
            .read_raw(dlcp_sim::memory::Address::from_raw(addr))
    }

    /// Write a single byte of CONTROL's data memory at the
    /// given physical address.  Mirror of gpsim's
    /// `_issue(f"reg(0xADDR)=0xVAL")` register-poke
    /// command, used by V1.71 tests that drive specific
    /// firmware paths via direct RAM writes (e.g.
    /// display_state_index, button-debounce, sentinels).
    fn write_reg(&mut self, addr: u16, value: u8) {
        self.inner.cores[self.i_ctl]
            .memory
            .write_raw(dlcp_sim::memory::Address::from_raw(addr), value);
    }

    /// Read a single byte of one MAIN's data memory at the
    /// given physical address.  `unit` selects which MAIN core
    /// (`0` for MAIN0, `1` for MAIN1); values 2..=255 raise
    /// `ValueError`.  Negative integers and values >255 are
    /// rejected by PyO3's u8 conversion before reaching the
    /// explicit branch below (with `OverflowError`).  On
    /// MAIN-only / single-MAIN chain topologies (where
    /// `i_main0 == i_main1`) both unit indices target the same
    /// physical core.
    ///
    /// Mirror of gpsim's per-MAIN register read in the wire-
    /// chain harnesses (`WireMultiMainChainHarness.main_reg`
    /// / `_main_reg`).  Used by Layer 5 wire-chain tests that
    /// inspect per-MAIN diag counters (`0x2E5..0x2EB`),
    /// per-MAIN state flags (`0x05E active_flags`), or
    /// per-MAIN preset / mute caches.
    fn read_main_reg(&self, unit: u8, addr: u16) -> PyResult<u8> {
        let i_main = match unit {
            0 => self.i_main0,
            1 => self.i_main1,
            other => {
                return Err(PyValueError::new_err(format!(
                    "read_main_reg: unit must be 0 or 1; got {other}"
                )));
            }
        };
        Ok(self.inner.cores[i_main]
            .memory
            .read_raw(dlcp_sim::memory::Address::from_raw(addr)))
    }

    /// Write a single byte of one MAIN's data memory at the
    /// given physical address.  `unit` selects which MAIN core
    /// (`0` for MAIN0, `1` for MAIN1); values 2..=255 raise
    /// `ValueError`.  Negative integers and values >255 are
    /// rejected by PyO3's u8 conversion before reaching the
    /// explicit branch below (with `OverflowError`).  Mirror
    /// of gpsim's per-MAIN register poke (used to seed diag
    /// counters, force standby state, etc.).
    fn write_main_reg(&mut self, unit: u8, addr: u16, value: u8) -> PyResult<()> {
        let i_main = match unit {
            0 => self.i_main0,
            1 => self.i_main1,
            other => {
                return Err(PyValueError::new_err(format!(
                    "write_main_reg: unit must be 0 or 1; got {other}"
                )));
            }
        };
        self.inner.cores[i_main]
            .memory
            .write_raw(dlcp_sim::memory::Address::from_raw(addr), value);
        Ok(())
    }

    /// Drive an external input pin on one MAIN's PORTx to the
    /// requested logic level.  Equivalent of gpsim's
    /// ``MainChainHarness(rc2_mode=...)`` continuous pin-level
    /// hold (codex task #75).  ``unit`` selects MAIN0 (0) or
    /// MAIN1 (1); ``port`` is "A", "B", or "C"; ``bit`` is
    /// 0..=7; ``level`` is True for HIGH, False for LOW.
    ///
    /// **Caveat (gpio.rs::drive_external_pin /
    /// is_general_input_pin):** the held level is only stored
    /// when the pin is currently a general input -- TRIS bit
    /// set, plus on RC4/RC5 the USB peripheral must not be
    /// overriding the pin (UCON.USBEN clear).  If TRIS is
    /// cleared (pin is output) at call time, the call is
    /// silently a no-op.  If firmware later flips TRIS to
    /// output, LATx takes over and the previously-held external
    /// level no longer drives the pin.  ANSEL/ANSELH analog
    /// masking is not modeled for the PIC18F2455 (MAIN) variant
    /// -- ``analog_digital_off_mask`` returns 0 for non-K20
    /// cores -- so a stored level always reads back on PORTx
    /// for MAIN pins regardless of ADCON1 PCFG bits.  This is
    /// fine for strap pins like RC2 (chain-mode select) that
    /// firmware never reconfigures, and for steady-state INTx
    /// / RBIF / RA0-wake stimuli; do not rely on "held level
    /// survives output" semantics for pins whose TRIS direction
    /// toggles during the test.
    fn set_main_pin(
        &mut self,
        unit: u8,
        port: &str,
        bit: u8,
        level: bool,
    ) -> PyResult<()> {
        let i_main = match unit {
            0 => self.i_main0,
            1 => self.i_main1,
            other => {
                return Err(PyValueError::new_err(format!(
                    "set_main_pin: unit must be 0 or 1; got {other}"
                )));
            }
        };
        let port_letter = parse_port_letter(port)
            .map_err(PyValueError::new_err)?;
        if bit >= 8 {
            return Err(PyValueError::new_err(format!(
                "set_main_pin: bit must be 0..=7; got {bit}"
            )));
        }
        if level {
            self.inner.set_pin_high(i_main, port_letter, bit);
        } else {
            self.inner.set_pin_low(i_main, port_letter, bit);
        }
        Ok(())
    }

    /// CONTROL-side equivalent of `set_main_pin`: drive an
    /// external input pin on CONTROL's PORTx to the requested
    /// logic level.  Same `gpio.rs::drive_external_pin` caveats
    /// apply (pin must currently be a general digital input;
    /// TRIS-to-output flip releases the held level).  Used by
    /// the RC5 IR pulse-train tests that drive RB5 with timed
    /// edges to exercise the actual `ir_rc5_decode` decoder
    /// rather than poking `ir_decoded_cmd` directly.
    fn set_control_pin(&mut self, port: &str, bit: u8, level: bool) -> PyResult<()> {
        let port_letter = parse_port_letter(port).map_err(PyValueError::new_err)?;
        if bit >= 8 {
            return Err(PyValueError::new_err(format!(
                "set_control_pin: bit must be 0..=7; got {bit}"
            )));
        }
        if level {
            self.inner.set_pin_high(self.i_ctl, port_letter, bit);
        } else {
            self.inner.set_pin_low(self.i_ctl, port_letter, bit);
        }
        Ok(())
    }

    /// Read a contiguous byte range from a core's program flash.
    /// Mirror of gpsim's `print mem 0xNN..0xMM` for code memory.
    /// Used to verify overlay-manifest preconditions before
    /// patching, and to confirm postconditions after.
    ///
    /// `core_idx` matches the `set_core_pc` / `step_until_pc_hit`
    /// mapping: 0=CONTROL, 1=MAIN0, 2=MAIN1.  `addr` is the
    /// silicon's byte-addressed program flash address; `length`
    /// is bytes (typical overlay sizes are 2-8 bytes).
    ///
    /// Spec / ledger ref: P4-followup E
    /// (`docs/SIM_REWRITE_RUST_PROGRESS.md` "P4 followup
    /// tracker", task #103) — building block for the rust
    /// standby-bypass overlay primitive that
    /// `test_v17_relocation::test_shifted_gpsim_with_dynamic_
    /// standby_overlay` migration needs.
    fn read_core_flash(
        &self,
        core_idx: usize,
        addr: u32,
        length: usize,
    ) -> PyResult<Vec<u8>> {
        let target_idx = match core_idx {
            0 => self.i_ctl,
            1 => self.i_main0,
            2 => self.i_main1,
            other => {
                return Err(PyValueError::new_err(format!(
                    "core_idx must be 0 (CONTROL), 1 (MAIN0), or 2 (MAIN1); got {}",
                    other,
                )));
            }
        };
        let flash = self.inner.cores[target_idx].flash();
        let start = addr as usize;
        let end = start.checked_add(length).ok_or_else(|| {
            PyValueError::new_err(format!(
                "addr (0x{addr:X}) + length ({length}) overflows usize"
            ))
        })?;
        if end > flash.len() {
            return Err(PyValueError::new_err(format!(
                "read_core_flash: addr=0x{addr:X} length={length} extends past \
                 flash end (flash_len=0x{flash_len:X})",
                flash_len = flash.len()
            )));
        }
        Ok(flash[start..end].to_vec())
    }

    /// Patch a contiguous byte range in a core's program flash.
    /// Mirror of gpsim's overlay-manifest mechanism: writes the
    /// supplied bytes into the loaded core image AFTER chain
    /// construction (so the firmware boots from a patched
    /// image without re-assembling the hex).
    ///
    /// Used by the rust-side standby-bypass overlay helper:
    /// to NOP the standby goto at `post_connect_init+2`, the
    /// caller passes `addr=post_connect_init_addr+2,
    /// bytes=b"\x00\x00\x00\x00"`.  Generic enough that future
    /// overlay-manifest equivalents (fast_boot, dsp_warmup_skip,
    /// etc.) can layer on the same primitive.
    ///
    /// `core_idx` is the same {0=CTL, 1=M0, 2=M1} mapping.
    /// Errors:
    ///   * `PyValueError` for unknown core_idx, or if addr +
    ///     bytes.len() extends past the flash end.
    ///
    /// Spec / ledger ref: P4-followup E
    /// (`docs/SIM_REWRITE_RUST_PROGRESS.md` "P4 followup
    /// tracker", task #103).
    fn patch_core_flash(
        &mut self,
        core_idx: usize,
        addr: u32,
        bytes: &[u8],
    ) -> PyResult<()> {
        let target_idx = match core_idx {
            0 => self.i_ctl,
            1 => self.i_main0,
            2 => self.i_main1,
            other => {
                return Err(PyValueError::new_err(format!(
                    "core_idx must be 0 (CONTROL), 1 (MAIN0), or 2 (MAIN1); got {}",
                    other,
                )));
            }
        };
        let flash = self.inner.cores[target_idx].flash_mut();
        let start = addr as usize;
        let end = start.checked_add(bytes.len()).ok_or_else(|| {
            PyValueError::new_err(format!(
                "addr (0x{addr:X}) + bytes.len ({len}) overflows usize",
                len = bytes.len()
            ))
        })?;
        if end > flash.len() {
            return Err(PyValueError::new_err(format!(
                "patch_core_flash: addr=0x{addr:X} bytes.len={len} extends past \
                 flash end (flash_len=0x{flash_len:X})",
                len = bytes.len(),
                flash_len = flash.len()
            )));
        }
        flash[start..end].copy_from_slice(bytes);
        Ok(())
    }

    /// CONTROL's K20-Tcy cycle counter at the current
    /// universal-clock tick.  Mirror of
    /// `control_gpsim.py::GpsimControlHarness.current_cycle`
    /// which tracks gpsim's `cycle` value (in Tcy) after the
    /// last `run` command.  The rust engine schedules cores
    /// on the universal-clock tick timeline; CONTROL's Tcy
    /// counter is `core.cycles()` directly.
    #[getter]
    fn current_cycle(&self) -> u64 {
        self.inner.cores[self.i_ctl].cycles()
    }

    /// No-op for rust backend.  Mirror of
    /// `control_gpsim.py::GpsimControlHarness.pause_heartbeat`,
    /// which suppresses gpsim's synthetic
    /// `heartbeat_rx_mode="full"` BF-reply pump used by
    /// the CONTROL-only harness to keep the firmware in
    /// CONNECTED mode without a real MAIN.  The rust
    /// facade has no synthetic-heartbeat mode -- the
    /// chain runs against a real V2.3-combined MAIN that
    /// emits actual BF replies -- so there is nothing to
    /// pause.  Provided for duck-typing parity with the
    /// gpsim test bodies.
    fn pause_heartbeat(&self) {}

    /// Inject synthetic 3-byte chain frames into MAIN's RX
    /// ring buffer (V3.x native_ring layout: ring base at
    /// physical 0x0200, depth 192 bytes; rd index at 0x0C6,
    /// wr index at 0x0C7).  Mirror of gpsim's
    /// `MainChainHarness.inject_frames_fifo` for
    /// `transport_mode="native_ring"`.  Frame-aligned
    /// overrun semantics: each 3-byte frame is either fully
    /// delivered or fully dropped (NOT split mid-frame).
    /// Returns `(delivered_bytes, overrun_bytes)`.
    ///
    /// `frames` is a list of 3-element byte sequences (route,
    /// cmd, data).  `fifo_limit` is capped at
    /// `MAIN_NATIVE_RX_SIZE - 1 = 191`; gpsim tests typically
    /// pass `fifo_limit=47` to mimic the V1.7 software-ring
    /// limit, but the V3.x native ring itself is 192 bytes.
    ///
    /// Targets the chain's `i_main` (which equals `i_ctl` in
    /// MAIN-only chains constructed via `from_v3x_main_only`,
    /// or the MAIN0 index in V1.x+V2.3 single-MAIN chains).
    /// Since this writes to the V3.x firmware's RAM-defined
    /// ring layout, callers must use it on a chain built
    /// with a V3.x MAIN hex.
    fn inject_main_frames_fifo(
        &mut self,
        frames: Vec<Vec<u8>>,
        fifo_limit: usize,
    ) -> (usize, usize) {
        const MAIN_NATIVE_RX_BASE: u16 = 0x0200;
        const MAIN_NATIVE_RX_SIZE: u16 = 0xC0; // 192 bytes
        const MAIN_RX_RING_RD: u16 = 0x0C6;
        const MAIN_RX_RING_WR: u16 = 0x0C7;

        let mem = &mut self.inner.cores[self.i_main0].memory;
        // Normalize rd/wr to [0, DEPTH) before any arithmetic or
        // address calculation -- mirrors the V1.71 RX-ring
        // hardening in inject_rx_bytes_inner so corrupt or
        // out-of-range RAM state can't underflow `wr + DEPTH - rd`
        // or write outside the 0x0200..0x02BF ring window.
        let rd = (mem.read_raw(dlcp_sim::memory::Address::from_raw(MAIN_RX_RING_RD)) as u16)
            % MAIN_NATIVE_RX_SIZE;
        let mut wr = (mem.read_raw(dlcp_sim::memory::Address::from_raw(MAIN_RX_RING_WR)) as u16)
            % MAIN_NATIVE_RX_SIZE;

        // Cap fifo_limit at MAIN_NATIVE_RX_SIZE - 1 (depth - 1
        // free-slot accounting matches gpsim's native_ring
        // semantics in chain_gpsim.py:705).
        let limit = fifo_limit.min((MAIN_NATIVE_RX_SIZE - 1) as usize).max(1);
        let mut delivered: usize = 0;
        let mut overruns: usize = 0;

        for frame in &frames {
            let used = ((wr + MAIN_NATIVE_RX_SIZE - rd) % MAIN_NATIVE_RX_SIZE) as usize;
            let free = limit.saturating_sub(used);
            if free < frame.len() {
                overruns += frame.len();
                continue;
            }
            for &byte in frame {
                let addr = MAIN_NATIVE_RX_BASE + wr;
                mem.write_raw(dlcp_sim::memory::Address::from_raw(addr), byte);
                wr = (wr + 1) % MAIN_NATIVE_RX_SIZE;
                delivered += 1;
            }
        }
        if delivered > 0 {
            mem.write_raw(
                dlcp_sim::memory::Address::from_raw(MAIN_RX_RING_WR),
                wr as u8,
            );
        }
        (delivered, overruns)
    }

    /// Read a single TAS3108 DSP subaddress register from the
    /// DSP slave coupled to MAIN0.  Mirror of gpsim's
    /// `MainChainHarness.read_i2c_regfile("dsp34", subaddr)`
    /// which reads the gpsim regfile module bound to MAIN's
    /// MSSP I²C bus.  For MAIN-only chains and multi-MAIN
    /// chains alike, this reads the FIRST DSP slave coupled
    /// to MAIN0 (which is the V3.x convention -- gpsim's
    /// MainChainHarness only attaches one regfile per MAIN).
    fn read_dsp_reg(&self, subaddr: u8) -> PyResult<u8> {
        let i_dsp = self.dsp_slave_index()?;
        Ok(self.inner.tas3108_slaves[i_dsp].read_subaddr(subaddr))
    }

    /// Program the address-NACK fault counter on the TAS3108
    /// slave coupled to MAIN0.  While `address_nack_count > 0`,
    /// the slave NACKs every address-phase byte that matches
    /// its own write or read address, then decrements.
    /// Used by the V3.1 robustness tests
    /// (`test_v31_review_findings.py`) to simulate persistent
    /// DSP unresponsiveness.  Mirror of gpsim's
    /// `MainChainHarness.set_i2c_fault("dsp34",
    /// address_nack_count=N)` (chain_gpsim.py:471) -- only the
    /// `address_nack_count` knob is implemented today; the
    /// other gpsim fault-injection knobs (address_stretch_*,
    /// data_nack_count, data_stuck_sda_*, stretch_scl_cycles)
    /// are stubs that raise NotImplementedError on the python
    /// facade.
    fn set_dsp_i2c_fault(&mut self, address_nack_count: u32) -> PyResult<()> {
        let i_dsp = self.dsp_slave_index()?;
        self.inner.tas3108_slaves[i_dsp].set_address_nack_count(address_nack_count);
        Ok(())
    }

    /// Clear all I²C fault-injection counters on the TAS3108
    /// slave coupled to MAIN0.  Mirror of gpsim's
    /// `MainChainHarness.clear_i2c_faults("dsp34")`
    /// (chain_gpsim.py:526) which resets address_nack +
    /// stretch + data_nack + stuck_sda back to defaults.
    /// In rust today only the `address_nack_count` counter
    /// exists; this method zeroes it.
    fn clear_dsp_i2c_faults(&mut self) -> PyResult<()> {
        let i_dsp = self.dsp_slave_index()?;
        self.inner.tas3108_slaves[i_dsp].clear_i2c_faults();
        Ok(())
    }

    /// Remaining address-NACK count on the TAS3108 slave coupled
    /// to MAIN0.  Mirror of gpsim's
    /// `MainChainHarness.read_i2c_attribute("dsp34",
    /// "Address_Nack_Count")` (`chain_gpsim.py` reader for the
    /// gpsim i2c-regfile attribute).  Used by deafness-chain
    /// regression tests that assert NACKs were consumed by
    /// firmware-driven I²C bursts: after
    /// `set_dsp_i2c_fault(address_nack_count=N)`, the firmware
    /// volume cmd should consume some of the budget, and the
    /// returned value will be `< N`.
    fn read_dsp_address_nack_count_remaining(&self) -> PyResult<u32> {
        let i_dsp = self.dsp_slave_index()?;
        Ok(self.inner.tas3108_slaves[i_dsp].address_nack_count_remaining())
    }

    /// Program the MSSP STOP-fault knobs on MAIN0's MSSP
    /// peripheral.  While `stop_busy_count != 0` and the
    /// firmware schedules a PEN-driven STOP, the
    /// state-machine deadline is extended by
    /// `stop_busy_cycles` Tcy beyond the normal SCL period
    /// before `complete_stop` clears PEN.  Mirror of gpsim's
    /// `MainChainHarness.set_mssp_stop_fault(
    /// stop_busy_cycles=N, stop_busy_count=M)`
    /// (chain_gpsim.py:451) used by V3.1 robustness tests
    /// to pin the firmware in i2c_wait_bus_idle while PEN
    /// appears stuck.
    fn set_mssp_stop_fault(&mut self, stop_busy_cycles: u32, stop_busy_count: i64) {
        self.inner.cores[self.i_main0]
            .peripherals
            .mssp
            .set_stop_fault(stop_busy_cycles, stop_busy_count);
    }

    /// Clear all MSSP fault-injection knobs on MAIN0's MSSP
    /// peripheral.  Mirror of gpsim's
    /// `MainChainHarness.clear_mssp_stop_faults()`
    /// (chain_gpsim.py:468).
    fn clear_mssp_stop_faults(&mut self) {
        self.inner.cores[self.i_main0]
            .peripherals
            .mssp
            .clear_stop_faults();
    }

    /// Force-abort any in-flight MSSP transaction on MAIN0
    /// and clear the SSPCON2 trigger bits.  Mirror of gpsim's
    /// `harness._issue("p18f2455.sspcon2 = 0")` workaround
    /// used by V3.1/V3.2 PEN-timeout-recovery tests: gpsim's
    /// SSPCON2.put() filter blocks normal firmware writes
    /// during active I²C, so the workaround uses a privileged
    /// register write that BOTH clears the SFR trigger bits
    /// AND ends the in-flight transaction (gpsim's MSSP
    /// polls SSPCON2 each tick and aborts when trigger bits
    /// are cleared externally).
    ///
    /// The rust MSSP state machine has its own
    /// `state: I2cState::Stop(N)` countdown that's
    /// independent of SSPCON2 memory contents -- so just
    /// writing 0 to SSPCON2 doesn't abort an in-flight
    /// STOP-fault-extended STOP.  This method does both:
    /// `mssp.reset_state()` -> Idle + writes 0 to SSPCON2
    /// memory, fully matching the gpsim privileged-write
    /// semantics.
    fn force_reset_main_mssp(&mut self) {
        let core = &mut self.inner.cores[self.i_main0];
        core.peripherals.mssp.reset_state();
        core.memory.write_raw(
            dlcp_sim::memory::Address::from_raw(dlcp_sim::peripherals::mssp::SSPCON2_ADDR),
            0,
        );
    }

    /// Set the AN0 (rail-sense ADC channel 0) sample for a
    /// specific MAIN core by unit index.  V3.x's
    /// `adc_boot_gate` (`src/dlcp_fw/asm/dlcp_main_v32.asm:4041`)
    /// busy-waits until the AN0 sample crosses `>= 0x0236`;
    /// runtime hysteresis is `0x0229/0x0228`.  The default
    /// seed for both MAINs is `0x0300` (well above threshold)
    /// per `build_v171_v32_chain` at lines 472/474.
    ///
    /// `unit` selects which MAIN core: `0` for MAIN0, `1` for
    /// MAIN1.  Other values raise `ValueError`.  On
    /// MAIN-only / single-MAIN chain topologies (where
    /// `i_main0 == i_main1`), both unit indices target the
    /// same physical core.
    ///
    /// `value` is the 10-bit ADC sample in the range
    /// `[0x0000, 0x03FF]` -- the PIC18F2455 ADC is 10-bit
    /// (datasheet DS39632E §21).  Values outside that range
    /// raise `ValueError` rather than silently masking, so a
    /// caller that passes a "12-bit-looking" word like `0x0500`
    /// gets a clear error instead of a sub-threshold sample.
    ///
    /// **Bug #45 H1 use case** (per
    /// `docs/analysis/TASK_45_ASYMMETRIC_WAKE_HYPOTHESES.md`):
    /// the H1 firmware-OBSERVABLE reproduction needs MAIN1 to
    /// run `wake_request_handler` (asm:1894 sets
    /// `active_flags.bit3`) BEFORE the AN0 droop applies; setting
    /// MAIN1's AN0 below threshold while MAIN1 is still in the
    /// post-STDBY standby loop prevents wake-byte dispatch in the
    /// rust sim and produces the H2 observable from #81 instead.
    /// Use AT or AFTER the wake byte's parser dispatch is
    /// observable: trigger on `MAIN1.active_flags.bit3 == 1` (RAM
    /// 0x05E bit 3) and then drop AN0 to `0x0100` -- the path
    /// from `wake_request_handler` exit through the main loop and
    /// `standby_event_dispatch` to the gate's first ADC
    /// conversion (asm:4048) traverses many MAIN-Tcy, leaving
    /// ample slack for the droop to land before the conversion
    /// latch.  See the rust-side test
    /// `multicore_parity.rs::v171_v32_v32_*_railcoupler*` for the
    /// fully-worked example.
    fn set_main_an0_sample(&mut self, unit: u8, value: u16) -> PyResult<()> {
        if value > 0x3FF {
            return Err(PyValueError::new_err(format!(
                "set_main_an0_sample: value must fit in 10 bits (0x0000..=0x03FF); \
                 got 0x{value:04X}. The PIC18F2455 ADC is 10-bit per DS39632E §21."
            )));
        }
        let i_main = match unit {
            0 => self.i_main0,
            1 => self.i_main1,
            other => {
                return Err(PyValueError::new_err(format!(
                    "set_main_an0_sample: unit must be 0 or 1; got {other}"
                )));
            }
        };
        self.inner.cores[i_main]
            .peripherals
            .adc
            .set_an0_sample(value);
        Ok(())
    }

    /// Write a single byte to CONTROL's EEPROM peripheral
    /// at the given 8-bit address (CONTROL EEPROM is 256
    /// bytes per PIC18F25K20 datasheet).  Mirror of
    /// gpsim's `eeprom_file=` constructor argument that
    /// preloads CONTROL's EEPROM HEX image before the
    /// simulation starts -- for rust callers that need to
    /// inject a single byte (e.g. the V1.71 preset-init
    /// tests that seed EEPROM[0x74]), this provides the
    /// minimum-viable per-byte poke.  Should be called
    /// AFTER chain construction but BEFORE the first
    /// step / warmup, since the firmware reads EEPROM
    /// during early boot.
    fn write_control_eeprom_byte(&mut self, addr: u8, value: u8) {
        self.inner.cores[self.i_ctl]
            .peripherals
            .eeprom
            .set_byte(addr, value);
    }

    /// Inject a 3-byte chain frame directly into CONTROL's
    /// RX ring buffer (V1.6b/V1.7/V1.71 layout: ring base
    /// at physical 0x066, parser-consumer index at 0x098,
    /// ISR-producer index at 0x099, depth 48 bytes per
    /// `dlcp_control_ram.inc`).  Mirror of
    /// `control_gpsim.py::GpsimControlHarness.inject_triplet`
    /// (ultimately routes through `_inject_rx_bytes`).
    /// Returns True if the bytes were enqueued, False if
    /// the ring was too full.  The firmware's parser will
    /// pick them up on the next idle scan -- callers
    /// should `step_many` or `step_ticks` afterwards to
    /// give the parser time to consume.
    fn inject_triplet(&mut self, route: u8, cmd: u8, data: u8) -> bool {
        self.inject_rx_bytes_inner(&[route, cmd, data])
    }

    /// Convenience over `inject_triplet`: V1.6b/V1.71 host-
    /// command injection.  Mirror of
    /// `control_gpsim.py::GpsimControlHarness.inject_host_command`.
    /// Default route is 0xBF (the parser dispatch tag the
    /// gpsim helper uses for HFD-over-BF host commands).
    #[pyo3(signature = (cmd, data, route=0xBF))]
    fn inject_host_command(&mut self, cmd: u8, data: u8, route: u8) -> bool {
        self.inject_triplet(route, cmd, data)
    }

    /// Inject a decoded IR event through the ISR handoff
    /// registers.  Mirror of
    /// `control_gpsim.py::GpsimControlHarness.inject_decoded_ir_event`:
    ///
    ///   * Optionally clear the IR debounce cells at 0x01B
    ///     and 0x01C (default `clear_debounce=True`).
    ///   * Write `cmd` to 0x01D and `addr` to 0x01E (the
    ///     decoded-IR cmd/addr ISR handoff cells).
    ///   * Clear bit 0 of 0x01F (control_flags.IR_ARMED)
    ///     so the foreground IR-dispatch path will run.
    ///
    /// Bypasses RB5 IR-waveform decoding -- this is a
    /// pure RAM poke through the same registers gpsim
    /// targets.  Caller is responsible for stepping
    /// afterwards to let the dispatch fire.
    #[pyo3(signature = (addr, cmd, clear_debounce=true))]
    fn inject_decoded_ir_event(&mut self, addr: u8, cmd: u8, clear_debounce: bool) {
        let mem = &mut self.inner.cores[self.i_ctl].memory;
        if clear_debounce {
            mem.write_raw(dlcp_sim::memory::Address::from_raw(0x01B), 0x00);
            mem.write_raw(dlcp_sim::memory::Address::from_raw(0x01C), 0x00);
        }
        mem.write_raw(dlcp_sim::memory::Address::from_raw(0x01D), cmd);
        mem.write_raw(dlcp_sim::memory::Address::from_raw(0x01E), addr);
        // Clear control_flags.IR_ARMED (bit 0 of 0x01F).
        let flags = mem.read_raw(dlcp_sim::memory::Address::from_raw(0x01F));
        mem.write_raw(dlcp_sim::memory::Address::from_raw(0x01F), flags & !0x01);
    }

    /// Snapshot CONTROL's TX byte history as a list of
    /// 3-byte `(route, cmd, data)` tuples.  Mirror of
    /// `control_gpsim.py::GpsimControlHarness.tx_frames`.
    /// The chain stores per-byte records in
    /// `uart_tx_history`; this method filters for bytes
    /// emitted from CONTROL (`src_core == i_ctl`) and groups
    /// every 3 consecutive bytes into a frame.  Trailing
    /// partial frames (history length not divisible by 3)
    /// are TRUNCATED -- gpsim's tx_frames is also frame-
    /// aligned, and a partial frame at the wire boundary
    /// would not yet be visible to the parser anyway.
    fn tx_frames(&self) -> Vec<(u8, u8, u8)> {
        let bytes: Vec<u8> = self
            .inner
            .uart_tx_history
            .iter()
            .filter(|r| r.src_core == self.i_ctl)
            .map(|r| r.byte)
            .collect();
        bytes.chunks_exact(3).map(|c| (c[0], c[1], c[2])).collect()
    }

    /// Return MAIN0's TX bytes recorded since the last call
    /// to this method (or since chain construction), then
    /// advance the capture pointer to the current end.
    /// Mirror of gpsim's
    /// `MainChainHarness.decoder.tx_record_since_last_capture()`
    /// pattern: tests inject a query frame, advance time
    /// until the firmware's response is fully drained, then
    /// inspect the captured bytes for byte-level assertions
    /// (e.g. cmd 0x21 high-nibble masking).
    ///
    /// On MAIN-only chains (no UART couplings), the
    /// `Chain::drain_completed_tx_bytes` path records each
    /// completed TX byte to `uart_tx_history` with
    /// `src_core == dst_core == src_core` (loopback
    /// sentinel) so the firmware's USART output is
    /// observable independent of any peer.
    fn tx_record_since_last_capture(&mut self) -> Vec<u8> {
        let main0 = self.i_main0;
        let main_records: Vec<u8> = self
            .inner
            .uart_tx_history
            .iter()
            .filter(|r| r.src_core == main0)
            .map(|r| r.byte)
            .collect();
        // Use the absolute monotonic counter
        // `uart_tx_total_by_src[main0]` to compute the byte
        // delta since the last mark.  Robust under rolling-
        // window truncation: if the buffer evicted older
        // records since the mark, the delta still reflects
        // the actual count of new bytes.  When the delta
        // exceeds the in-buffer matching count (because
        // truncation evicted some of those new bytes), we
        // return the available tail and the caller can
        // detect the loss via `uart_tx_history_dropped`.
        // Codex MEDIUM #2 from review of 0be5299.
        let total_now = self.inner.uart_tx_total_by_src[main0];
        let want = total_now.saturating_sub(self.tx_capture_main0) as usize;
        let in_buffer = main_records.len();
        let take = want.min(in_buffer);
        let start = in_buffer - take;
        let result = main_records[start..].to_vec();
        self.tx_capture_main0 = total_now;
        result
    }

    /// Reset the TX capture pointer to the current end of
    /// MAIN0's recorded TX history -- subsequent
    /// `tx_record_since_last_capture` calls only see bytes
    /// pushed AFTER this call.  Use when the test wants to
    /// drop pre-stimulus bytes (boot-time TX, prior query
    /// responses) before injecting the next stimulus.
    fn mark_tx_capture_point(&mut self) {
        // Mark = absolute total at this instant.  Subsequent
        // `tx_record_since_last_capture` returns
        // (total_now - mark) bytes from the rolling window.
        // Codex MEDIUM #2 from review of 0be5299: previously
        // this stored a filtered-buffer count, which became
        // stale on rolling-window eviction.
        let main0 = self.i_main0;
        self.tx_capture_main0 = self.inner.uart_tx_total_by_src[main0];
    }

    /// MAIN1 mirror of `mark_tx_capture_point` for 3-core
    /// wire-chain probes that need to localize byte loss
    /// between MAIN1 TX and CONTROL RX.  In the V1.71+V3.2+V3.2
    /// ring topology (CTL.tx -> MAIN0.rx -> MAIN1.rx -> CTL.rx),
    /// MAIN0's BF/2N reply burst flows through MAIN1's
    /// forwarder before reaching CONTROL.  Comparing
    /// MAIN0 TX, MAIN1 TX, and CONTROL RX accept counts
    /// localizes which hop drops bytes.  Single-MAIN chains
    /// alias `i_main1 == i_main0`, so this returns the same
    /// stream as `mark_tx_capture_point` and offers no new
    /// information.  See task #94.
    fn mark_main1_tx_capture_point(&mut self) {
        // Same absolute-counter semantics as
        // `mark_tx_capture_point` (codex MEDIUM #2).
        let main1 = self.i_main1;
        self.tx_capture_main1 = self.inner.uart_tx_total_by_src[main1];
    }

    /// MAIN1 mirror of `tx_record_since_last_capture`.
    /// Returns MAIN1's TX bytes recorded since the last
    /// `mark_main1_tx_capture_point()` call (or since chain
    /// construction if never marked), then advances the
    /// capture pointer to the current end.  Bytes are
    /// returned as a flat list of u8s; alignment to 3-byte
    /// chain frames is the caller's responsibility.  See
    /// task #94.
    fn main1_tx_record_since_last_capture(&mut self) -> Vec<u8> {
        // Same absolute-counter slicing as
        // `tx_record_since_last_capture` (codex MEDIUM #2).
        let main1 = self.i_main1;
        let main1_records: Vec<u8> = self
            .inner
            .uart_tx_history
            .iter()
            .filter(|r| r.src_core == main1)
            .map(|r| r.byte)
            .collect();
        let total_now = self.inner.uart_tx_total_by_src[main1];
        let want = total_now.saturating_sub(self.tx_capture_main1) as usize;
        let in_buffer = main1_records.len();
        let take = want.min(in_buffer);
        let start = in_buffer - take;
        let result = main1_records[start..].to_vec();
        self.tx_capture_main1 = total_now;
        result
    }

    /// Reset the CTL-side RX capture pointer to the current
    /// end of `Chain::uart_rx_history` filtered by
    /// `dst_core == i_ctl`.  Mirror of
    /// `mark_ctl_tx_capture_point` but on the destination
    /// side: only bytes the destination's silicon FIFO
    /// ACCEPTED (passed SPEN+CREN, not blocked by OERR, FIFO
    /// had room).  Subsequent `ctl_rx_record_since_last_capture`
    /// calls return only bytes pushed AFTER this point.
    /// See task #94.
    fn mark_ctl_rx_capture_point(&mut self) {
        let ctl = self.i_ctl;
        self.rx_capture_ctl = self.inner.uart_rx_total_by_dst[ctl];
    }

    /// Return CONTROL's RX-accepted bytes since the last
    /// `mark_ctl_rx_capture_point()` call.  Distinct from
    /// `ctl_tx_record_since_last_capture` (CONTROL's outgoing
    /// bytes) and from filtering `uart_tx_history` by
    /// `dst_core == i_ctl` (which records wire-attempts
    /// pre-acceptance).  See task #94.
    fn ctl_rx_record_since_last_capture(&mut self) -> Vec<u8> {
        let ctl = self.i_ctl;
        let ctl_records: Vec<u8> = self
            .inner
            .uart_rx_history
            .iter()
            .filter(|r| r.dst_core == ctl)
            .map(|r| r.byte)
            .collect();
        let total_now = self.inner.uart_rx_total_by_dst[ctl];
        let want = total_now.saturating_sub(self.rx_capture_ctl) as usize;
        let in_buffer = ctl_records.len();
        let take = want.min(in_buffer);
        let start = in_buffer - take;
        let result = ctl_records[start..].to_vec();
        self.rx_capture_ctl = total_now;
        result
    }

    /// MAIN0 mirror of `mark_ctl_rx_capture_point`.
    fn mark_main0_rx_capture_point(&mut self) {
        let main0 = self.i_main0;
        self.rx_capture_main0 = self.inner.uart_rx_total_by_dst[main0];
    }

    /// MAIN0 mirror of `ctl_rx_record_since_last_capture`.
    fn main0_rx_record_since_last_capture(&mut self) -> Vec<u8> {
        let main0 = self.i_main0;
        let main0_records: Vec<u8> = self
            .inner
            .uart_rx_history
            .iter()
            .filter(|r| r.dst_core == main0)
            .map(|r| r.byte)
            .collect();
        let total_now = self.inner.uart_rx_total_by_dst[main0];
        let want = total_now.saturating_sub(self.rx_capture_main0) as usize;
        let in_buffer = main0_records.len();
        let take = want.min(in_buffer);
        let start = in_buffer - take;
        let result = main0_records[start..].to_vec();
        self.rx_capture_main0 = total_now;
        result
    }

    /// MAIN1 mirror of `mark_ctl_rx_capture_point`.
    fn mark_main1_rx_capture_point(&mut self) {
        let main1 = self.i_main1;
        self.rx_capture_main1 = self.inner.uart_rx_total_by_dst[main1];
    }

    /// MAIN1 mirror of `ctl_rx_record_since_last_capture`.
    fn main1_rx_record_since_last_capture(&mut self) -> Vec<u8> {
        let main1 = self.i_main1;
        let main1_records: Vec<u8> = self
            .inner
            .uart_rx_history
            .iter()
            .filter(|r| r.dst_core == main1)
            .map(|r| r.byte)
            .collect();
        let total_now = self.inner.uart_rx_total_by_dst[main1];
        let want = total_now.saturating_sub(self.rx_capture_main1) as usize;
        let in_buffer = main1_records.len();
        let take = want.min(in_buffer);
        let start = in_buffer - take;
        let result = main1_records[start..].to_vec();
        self.rx_capture_main1 = total_now;
        result
    }

    /// CONTROL-side equivalent of `mark_tx_capture_point`.
    /// Records the count of `uart_tx_history` entries whose
    /// `src_core == i_ctl` so the next call to
    /// `ctl_tx_record_since_last_capture` only returns bytes
    /// pushed AFTER this point.  Used by tests that need to
    /// bound CONTROL-TX observation to a specific firmware-PC
    /// window (mark before injecting an IR event, capture
    /// after stepping until the next periodic full-sync hook
    /// entry).
    fn mark_ctl_tx_capture_point(&mut self) {
        let ctl = self.i_ctl;
        self.tx_capture_ctl = self.inner.uart_tx_total_by_src[ctl];
    }

    /// CONTROL-side equivalent of `tx_record_since_last_
    /// capture`.  Returns CONTROL's TX bytes recorded since
    /// the last `mark_ctl_tx_capture_point()` call (or since
    /// chain construction if never marked), then advances the
    /// capture pointer to the current end.  Bytes are returned
    /// as a flat list of u8s; alignment to 3-byte chain frames
    /// is the caller's responsibility.
    fn ctl_tx_record_since_last_capture(&mut self) -> Vec<u8> {
        let ctl = self.i_ctl;
        let ctl_records: Vec<u8> = self
            .inner
            .uart_tx_history
            .iter()
            .filter(|r| r.src_core == ctl)
            .map(|r| r.byte)
            .collect();
        let total_now = self.inner.uart_tx_total_by_src[ctl];
        let want = total_now.saturating_sub(self.tx_capture_ctl) as usize;
        let in_buffer = ctl_records.len();
        let take = want.min(in_buffer);
        let start = in_buffer - take;
        let result = ctl_records[start..].to_vec();
        self.tx_capture_ctl = total_now;
        result
    }

    /// Snapshot the FULL `uart_tx_history` as a list of
    /// `(tick, src_core, dst_core, byte)` tuples (every wire-
    /// attempt byte from chain construction onward, no
    /// drainage, no filter).  Caller is responsible for
    /// filtering by src/dst and slicing by tick range.  Used
    /// by frame-level timeline probes that need byte-by-byte
    /// timestamps to compute inter-frame gaps and per-phase
    /// throughput.  Cost: O(N) Vec clone where N is the full
    /// history length; for steady-state probes prefer to
    /// `apply_reset_all` (clears history) at probe-start and
    /// dump only the post-reset records.
    fn uart_tx_records_full(&self) -> Vec<(u64, usize, usize, u8)> {
        self.inner
            .uart_tx_history
            .iter()
            .map(|r| (r.tick, r.src_core, r.dst_core, r.byte))
            .collect()
    }

    /// Per-link fault primitive.  Rust mirror of gpsim's
    /// `WireMultiMainChainHarness::set_link_fault(link_name, *,
    /// drop, extra_cycles)`.  Spec / ledger: P4-followup C
    /// (`docs/SIM_REWRITE_RUST_PROGRESS.md` "P4 followup tracker",
    /// task #101) — unblocks the wire-chain fault-injection
    /// tests (`test_wire_chain_gpsim*.py`,
    /// `test_reconnect_wake_gate.py`, etc.) on the rust backend.
    ///
    /// `link_name` follows the same role-based naming as
    /// `bridge_byte_stats()` -- e.g. `ctl_to_m0`, `m0_to_m1`,
    /// `m1_to_ctl` for the rust 3-core ring topology.  Tests
    /// that hard-code gpsim's bus-model labels (e.g.
    /// `m0_to_ctl`, which doesn't exist on the rust ring) will
    /// raise `KeyError` listing the known links -- same
    /// exception type as gpsim's own "unknown wire link"
    /// failure (codex LOW from 4307acc: prior implementation
    /// used `ValueError`).
    ///
    /// `drop`: `True` activates the wire-drop fault on this
    /// coupling (every subsequent byte the source TXs is
    /// silently dropped at the wire layer; the destination
    /// never sees it).  `False` clears the fault (counter
    /// returns to 0).  `None` leaves the drop state unchanged
    /// (matches gpsim's three-state semantics).  Internally
    /// the drop activation sets the underlying counter to
    /// `u32::MAX` so the fault persists indefinitely until
    /// the next `set_link_fault(..., drop=False)`.
    ///
    /// `extra_cycles`: NOT implemented on the rust silicon
    /// ring.  The rust chain delivers UART bytes immediately
    /// when the source's TX shift register completes
    /// (silicon-correct -- the bus is current-loop with no
    /// buffering middleware), so "extra delay between source
    /// TX and destination RX" is not a meaningful quantity
    /// here.  Calling with `extra_cycles != None` raises
    /// `NotImplementedError`.  Tests that need bridge
    /// propagation-delay semantics must be marked gpsim-only.
    /// (Codex LOW from 4307acc: prior keyword was `extra_ticks`
    /// and exception was `RuntimeError`; both are aligned to
    /// gpsim now.)
    #[pyo3(signature = (link_name, *, drop=None, extra_cycles=None))]
    fn set_link_fault(
        &mut self,
        link_name: &str,
        drop: Option<bool>,
        extra_cycles: Option<u64>,
    ) -> PyResult<()> {
        if extra_cycles.is_some() {
            return Err(PyNotImplementedError::new_err(
                "Chain.set_link_fault(extra_cycles=...) is not supported on \
                 the rust silicon ring (no bridge-delay model; mark this \
                 test gpsim-only).  Spec ref: \
                 docs/SIM_REWRITE_RUST_PROGRESS.md 'P4 followup tracker' \
                 task #101.",
            ));
        }
        let coupling_idx = self.uart_coupling_idx_for_link(link_name)?;
        if let Some(drop) = drop {
            let drop_count = if drop { u32::MAX } else { 0 };
            self.inner.set_uart_coupling_drop(coupling_idx, drop_count);
        }
        Ok(())
    }

    /// Helper for `set_link_fault` and `bridge_byte_stats`:
    /// resolve a role-based link name to an index into
    /// `self.inner.pinnet.uart`.  Raises `KeyError` (matching
    /// gpsim's `KeyError` from `set_link_fault` on the same
    /// condition) listing the known links if the name doesn't
    /// match any wired coupling.
    fn uart_coupling_idx_for_link(&self, link_name: &str) -> PyResult<usize> {
        let mut known: Vec<String> = Vec::with_capacity(self.inner.pinnet.uart.len());
        let role_of = |core_idx: usize| -> String {
            if core_idx == self.i_ctl {
                "ctl".to_string()
            } else if core_idx == self.i_main0 {
                "m0".to_string()
            } else if core_idx == self.i_main1 {
                "m1".to_string()
            } else {
                format!("c{core_idx}")
            }
        };
        for (idx, coupling) in self.inner.pinnet.uart.iter().enumerate() {
            let name = format!(
                "{}_to_{}",
                role_of(coupling.src_core),
                role_of(coupling.dst_core),
            );
            if name == link_name {
                return Ok(idx);
            }
            known.push(name);
        }
        Err(PyKeyError::new_err(format!(
            "unknown wire link {link_name:?}; known links on this rust chain: {}",
            known.join(", ")
        )))
    }

    /// Per-link byte-count snapshot for every UART coupling
    /// actually wired in the chain.  Mirror-of-shape (NOT
    /// mirror-of-name) of gpsim's
    /// `WireMultiMainChainHarness::bridge_shift_stats`: returns
    /// `dict[link_name, dict[counter_name, value]]` so a
    /// dual-backend canary test can call
    /// `pre_stats = chain.bridge_byte_stats()` and compute
    /// per-link deltas with identical Python code on either
    /// backend.
    ///
    /// **Topology divergence vs gpsim** (codex MEDIUM from
    /// 48a862d): the rust 3-core chain in `from_v171_v32` wires
    /// a TRUE ring -- `CONTROL -> MAIN0 -> MAIN1 -> CONTROL`
    /// (3 unidirectional UART couplings).  gpsim's wire-chain
    /// bus model exposes 4 named hops
    /// (`ctl_to_m0`, `m0_to_m1`, `m1_to_m0`, `m0_to_ctl`)
    /// because both directions of the M0-M1 link AND a
    /// MAIN0->CONTROL forwarder are simulated as separate
    /// bridges to model bit-level current-loop bus arbitration.
    /// Rather than hard-coding gpsim's four labels (and
    /// reporting two of them as always-0 -- which would
    /// mis-attribute a real future PB2 reply through the
    /// `m1_to_ctl` ring leg), this method enumerates the
    /// chain's actual `pinnet.uart` couplings and labels them
    /// by core role.  Concrete output for `from_v171_v32`:
    ///
    ///   * `ctl_to_m0`  -- CONTROL TX -> MAIN0 RX
    ///   * `m0_to_m1`   -- MAIN0 TX  -> MAIN1 RX
    ///   * `m1_to_ctl`  -- MAIN1 TX  -> CONTROL RX (rust ring's
    ///                     upstream return, equivalent role to
    ///                     gpsim's `m0_to_ctl` but routed
    ///                     directly per silicon)
    ///
    /// For unrecognised core roles (single-MAIN chains, etc.)
    /// the label format is `c{src_core}_to_c{dst_core}` so the
    /// caller can still observe traffic on every coupling.
    ///
    /// Counter shape: returns `total_edges` (byte count) plus
    /// gpsim-parity placeholders `shift_events`,
    /// `total_shift_cycles`, `max_shift_cycles` (all 0 -- rust
    /// silicon ring delivers whole bytes; bit-level batching
    /// is a gpsim-only concept).  Callers asserting on
    /// `total_edges > 0` get identical-shape pre/post deltas
    /// across backends; callers reading the bit-level keys
    /// must know they are gpsim-only.
    ///
    /// Cost: O(N) where N is the full
    /// `Chain::uart_tx_history`.  Acceptable for canary tests
    /// snapshotting pre/post around a sub-second window;
    /// long-running tests should call sparingly.
    ///
    /// Spec / ledger ref: P4-followup A
    /// (`docs/SIM_REWRITE_RUST_PROGRESS.md` "P4 followup
    /// tracker", task #99).
    fn bridge_byte_stats(&self) -> std::collections::HashMap<String, std::collections::HashMap<String, u64>> {
        let mut out: std::collections::HashMap<String, std::collections::HashMap<String, u64>> =
            std::collections::HashMap::with_capacity(self.inner.pinnet.uart.len());
        // Build a lookup from core_idx -> short role name so
        // the produced labels (`ctl_to_m0`, `m0_to_m1`, etc.)
        // match gpsim's hop names where the topology overlaps.
        let role_of = |core_idx: usize| -> String {
            if core_idx == self.i_ctl {
                "ctl".to_string()
            } else if core_idx == self.i_main0 {
                "m0".to_string()
            } else if core_idx == self.i_main1 {
                "m1".to_string()
            } else {
                format!("c{core_idx}")
            }
        };
        for coupling in &self.inner.pinnet.uart {
            let src = coupling.src_core;
            let dst = coupling.dst_core;
            let name = format!("{}_to_{}", role_of(src), role_of(dst));
            let count = self
                .inner
                .uart_tx_history
                .iter()
                .filter(|r| r.src_core == src && r.dst_core == dst)
                .count() as u64;
            let mut sub: std::collections::HashMap<String, u64> =
                std::collections::HashMap::with_capacity(4);
            sub.insert("total_edges".to_string(), count);
            // gpsim parity placeholders -- rust silicon ring
            // doesn't track bit-level edges, so these stay 0.
            sub.insert("shift_events".to_string(), 0);
            sub.insert("total_shift_cycles".to_string(), 0);
            sub.insert("max_shift_cycles".to_string(), 0);
            out.insert(name, sub);
        }
        out
    }

    /// Snapshot the FULL `uart_rx_history` (FIFO-accepted
    /// bytes) as `(tick, src_core, dst_core, byte)` tuples.
    /// Distinct from `uart_tx_records_full`: this records
    /// only bytes the destination's silicon FIFO accepted
    /// (passed SPEN+CREN, not blocked by OERR, FIFO had
    /// room).  Comparing the two streams localizes byte
    /// loss between wire and parser.  Same cost caveat as
    /// `uart_tx_records_full`.
    fn uart_rx_records_full(&self) -> Vec<(u64, usize, usize, u8)> {
        self.inner
            .uart_rx_history
            .iter()
            .map(|r| (r.tick, r.src_core, r.dst_core, r.byte))
            .collect()
    }

    /// CONTROL core's current PC (firmware program counter).
    /// Direct passthrough to `Core::pc()`.  Word-aligned and
    /// masked to 21 bits.  Mirror of gpsim's `pc()` register
    /// readable via `_issue("pc")`, used by tests that need
    /// to know the firmware's instruction-stream position
    /// (e.g. to detect when a periodic loop-head is reached).
    fn current_ctl_pc(&self) -> u32 {
        self.inner.cores[self.i_ctl].pc()
    }

    /// MAIN0 core's current PC (firmware program counter).
    /// Direct passthrough to `Core::pc()`.  Word-aligned and
    /// masked to 21 bits.  For symmetry with `current_ctl_pc`.
    fn current_main_pc(&self) -> u32 {
        self.inner.cores[self.i_main0].pc()
    }

    /// Step the chain until the selected core's PC enters
    /// [`pc_lo`, `pc_hi`] (inclusive), or `max_tcy` Tcy
    /// elapse.  Returns the actual PC observed at exit (which
    /// may be outside the range if the budget was exhausted --
    /// callers can detect "didn't hit" by comparing the return
    /// value against the range).  Quantization: stepping
    /// happens in `chunk_tcy = 100` Tcy chunks, so the
    /// firmware may step a few instructions past the target PC
    /// before the loop notices.  Use this to align observation
    /// windows to firmware-loop-head events (e.g. function_028
    /// entry on V1.6b CONTROL is at 0x0B36; pass
    /// `core_idx=0, pc_lo=0x0B36, pc_hi=0x0B38` to step until
    /// CONTROL is at the entry).  Mirror of gpsim's
    /// `break e <addr>` + `run` primitive for the K20 / 2455
    /// cores.
    ///
    /// `core_idx` selects the core to inspect:
    ///   * 0 -> CONTROL (`i_ctl`)
    ///   * 1 -> MAIN0 (`i_main0`)
    ///   * 2 -> MAIN1 (`i_main1`) — extended 2026-05-04
    ///     for ledger task #100 (executor breakpoint
    ///     primitives), unblocking the
    ///     `test_v31_combined_dsp_table_apply.py` family
    ///     and other 2-MAIN gpsim probes.
    /// Other values raise `PyValueError`.
    #[pyo3(signature = (core_idx, pc_lo, pc_hi, max_tcy=1_000_000))]
    fn step_until_pc_hit(
        &mut self,
        core_idx: usize,
        pc_lo: u32,
        pc_hi: u32,
        max_tcy: u64,
    ) -> PyResult<u32> {
        let target_idx = match core_idx {
            0 => self.i_ctl,
            1 => self.i_main0,
            2 => self.i_main1,
            other => {
                return Err(PyValueError::new_err(format!(
                    "core_idx must be 0 (CONTROL), 1 (MAIN0), or 2 (MAIN1); got {}",
                    other,
                )));
            }
        };
        if pc_hi < pc_lo {
            return Err(PyValueError::new_err(format!(
                "pc_hi (0x{:06X}) must be >= pc_lo (0x{:06X})",
                pc_hi, pc_lo,
            )));
        }
        const CHUNK_TCY: u64 = 100;
        let factor = self.tcy_factor();
        let mut remaining = max_tcy;
        loop {
            let pc = self.inner.cores[target_idx].pc();
            if pc >= pc_lo && pc <= pc_hi {
                return Ok(pc);
            }
            if remaining == 0 {
                return Ok(pc);
            }
            let advance = CHUNK_TCY.min(remaining);
            self.inner.step_ticks(advance * factor);
            remaining -= advance;
        }
    }

    /// Override a core's program counter mid-run.  Mirror of
    /// gpsim's `pc=0x...` CLI primitive.  Spec / ledger:
    /// P4-followup B (`docs/SIM_REWRITE_RUST_PROGRESS.md`
    /// "P4 followup tracker", task #100) — together with
    /// `step_until_pc_hit` this gives Python tests the
    /// `pc=X ; break e Y ; run` pattern that
    /// `test_v31_combined_dsp_table_apply.py` (5 tests),
    /// `test_v30_gpsim_equivalence.py` (10 tests), and
    /// parts of `test_v30_relocation.py` use to drive
    /// PIC18 helper routines from arbitrary entry points.
    ///
    /// `core_idx` matches `step_until_pc_hit`'s mapping:
    ///   * 0 -> CONTROL (`i_ctl`)
    ///   * 1 -> MAIN0 (`i_main0`)
    ///   * 2 -> MAIN1 (`i_main1`)
    ///
    /// `pc` is the silicon's word-addressed PC in the
    /// `[0, 0x001F_FFFF]` range; per
    /// `Core::set_pc`'s contract, bit 0 is masked to 0
    /// (PC is instruction-aligned, not byte-aligned, on
    /// PIC18).  Returns the masked PC actually written so
    /// the caller can detect the bit-0 strip without a
    /// follow-up read.
    #[pyo3(signature = (core_idx, pc))]
    fn set_core_pc(&mut self, core_idx: usize, pc: u32) -> PyResult<u32> {
        let target_idx = match core_idx {
            0 => self.i_ctl,
            1 => self.i_main0,
            2 => self.i_main1,
            other => {
                return Err(PyValueError::new_err(format!(
                    "core_idx must be 0 (CONTROL), 1 (MAIN0), or 2 (MAIN1); got {}",
                    other,
                )));
            }
        };
        self.inner.cores[target_idx].set_pc(pc);
        Ok(self.inner.cores[target_idx].pc())
    }

    /// Advance simulation until MAIN0 stops emitting TX
    /// bytes for `quiescent_tcy` consecutive Tcy, or up to
    /// `max_tcy` total Tcy.  Returns the number of Tcy
    /// actually advanced (<= max_tcy).  Mirror of gpsim's
    /// `chain.step_until_tx_quiescent()` pattern: the
    /// firmware finishes responding to a query when the
    /// USART TXREG/TRMT pair stays empty for a "long
    /// enough" interval.
    ///
    /// Quiescence is checked in fixed `quiescent_tcy`
    /// chunks: advance one chunk, see if any new MAIN0 TX
    /// records arrived since the last chunk; if not AND at
    /// least one TX byte has been observed during this call
    /// (when `require_tx_activity = True`), declare
    /// quiescent.
    ///
    /// `require_tx_activity` (default True): wait for at
    /// least one TX byte to appear before applying the
    /// quiescence check.  Without this guard the function
    /// would return immediately on the first chunk if the
    /// firmware hasn't yet started responding -- giving the
    /// caller an empty TX-record buffer and the false
    /// impression that the response already completed.
    /// Pass False if the test wants the bare "no activity
    /// for one chunk" semantics (e.g. asserting that NO
    /// response is generated under some condition).
    ///
    /// Defaults: `quiescent_tcy` = 10_000 Tcy (~2.5 ms at
    /// 4 MIPS, comfortably longer than a 31_250-baud frame
    /// at ~320 us/byte); `max_tcy` = 5_000_000 Tcy (~1.25 s
    /// sim time, long enough for a multi-frame burst
    /// response).
    #[pyo3(signature = (quiescent_tcy=10_000, max_tcy=5_000_000, require_tx_activity=true))]
    fn step_until_tx_quiescent(
        &mut self,
        quiescent_tcy: u64,
        max_tcy: u64,
        require_tx_activity: bool,
    ) -> u64 {
        // Clamp `quiescent_tcy` to at least 1 so the chunk
        // size is always positive; otherwise the loop would
        // spin forever (chunk=0 -> advanced never increases).
        let quiescent_tcy = quiescent_tcy.max(1);
        let main0 = self.i_main0;
        let factor = self.tcy_factor();
        let count_main_records = |inner: &RustChain| -> usize {
            inner
                .uart_tx_history
                .iter()
                .filter(|r| r.src_core == main0)
                .count()
        };
        let mut advanced: u64 = 0;
        let initial_count = count_main_records(&self.inner);
        let mut last_count = initial_count;
        while advanced < max_tcy {
            let chunk = quiescent_tcy.min(max_tcy - advanced);
            self.inner.step_ticks(chunk * factor);
            advanced += chunk;
            let new_count = count_main_records(&self.inner);
            let saw_tx_this_call = new_count > initial_count;
            if new_count == last_count && (saw_tx_this_call || !require_tx_activity) {
                // No new TX bytes during this chunk and (we've
                // already seen at least one TX byte this call,
                // or the caller doesn't require activity).
                return advanced;
            }
            last_count = new_count;
        }
        advanced
    }

    /// Step a fixed `DEFAULT_STEP_TCY`-Tcy convenience
    /// chunk (200K Tcy).  Provides the same parameterless-
    /// step interface the gpsim harness exposes, so duck-
    /// typed scenario helpers (`_press_sequence`,
    /// `_rx_sequence`, `_ir_event`) work on either backend.
    /// When a test needs a specific amount of simulated
    /// time, call `step_tcy(N)` instead.
    ///
    /// Tcy interpretation matches `step_tcy`: MAIN-only
    /// chains use the PIC18F2455 factor (12 ticks/Tcy,
    /// 2.4 M ticks total); K20 chains -- mixed CONTROL+MAIN
    /// AND CONTROL-only -- use the K20 factor (16 ticks/Tcy,
    /// 3.2 M ticks total).  See `tcy_factor`.
    fn step(&mut self) {
        if self.force_connected {
            self.apply_force_connected_hook();
        }
        self.inner.step_ticks(DEFAULT_STEP_TCY * self.tcy_factor());
    }

    /// Run the chain to a CONNECTED steady-state by stepping
    /// `cycles` Tcy worth of universal ticks.  Mirror of
    /// `control_gpsim.py::GpsimControlHarness.warmup` for
    /// chains that DON'T need the heartbeat-force-connected
    /// hook (i.e. those built with a real MAIN peer that
    /// drives BF replies on the UART).  For CONTROL-only
    /// chains, use `warmup_force_connected(cycles)` instead.
    /// `cycles` is in K20 instruction cycles (Tcy); each
    /// Tcy is 16 universal ticks for the K20 core, so the
    /// total advance is `cycles * 16` ticks.  No early-exit
    /// predicate -- the test's _WARMUP_CYCLES (25 M Tcy =
    /// 400 M ticks ≈ 8.3 s sim) is empirically sized to
    /// cover both the cold-boot handshake AND a few
    /// post-handshake polls.
    fn warmup(&mut self, cycles: u64) {
        self.inner.step_ticks(cycles * 16);
    }

    /// Enable the per-step "force CONNECTED" hook that mirrors
    /// gpsim's `GpsimControlHarness(heartbeat_force_connected=
    /// True)`.  After this is called, every subsequent `step()`
    /// applies the pokes documented on
    /// `apply_force_connected_hook` (OR 0x0A into 0x01F, reset
    /// 0x09D/0x09E to 0xFF) BEFORE advancing time.
    ///
    /// `warmup_force_connected()` honours this flag for post-
    /// warmup `step()` calls but applies its own
    /// `display_entered` gate during the warmup loop itself
    /// (the hook is NOT applied pre-DISPLAY -- mirror of
    /// gpsim's `_heartbeat_active` gate; codex MEDIUM-2 from
    /// review of ac6eb09).  See `warmup_force_connected` for
    /// the full flow.
    ///
    /// Used by CONTROL-only chains that must keep the firmware
    /// in DISPLAY mode without a real MAIN peer driving BF
    /// replies.  No-op (idempotent) once enabled.
    fn enable_force_connected(&mut self) {
        self.force_connected = true;
    }

    /// Inject 3-byte chain frames (BF/cmd/data) into CONTROL's
    /// RX ring at base 0x066 (depth 48 bytes; rd=0x098,
    /// wr=0x099).  Mirror of gpsim's
    /// `_CliSession::_inject_rx_bytes`.  Returns False if the
    /// ring is too full (>= 0x2C bytes pending) and silently
    /// drops the burst -- callers should let the firmware drain
    /// the ring and retry.  `bytes` is a flat list of byte
    /// values; alignment to 3-byte frames is the caller's
    /// responsibility.
    fn inject_control_rx_bytes(&mut self, bytes: Vec<u8>) -> bool {
        self.inject_control_rx_bytes_inner(&bytes)
    }

    /// Run a CONTROL-only chain through cold-boot -> WAITING ->
    /// DISPLAY transition by feeding the firmware synthetic BF
    /// status replies (5-frame `BF/05/33 BF/07/60 BF/03/01
    /// BF/06/00 BF/1D/00`) until DISPLAY mode is detected
    /// (0x01F.bit1 set BY THE FIRMWARE ITSELF), then continues
    /// stepping with the force-connected hook applied each
    /// chunk to keep CONNECTED + event-exit asserted.  Mirror of
    /// `GpsimControlHarness.warmup` when the harness was
    /// constructed with `heartbeat_rx_mode in {"full",
    /// "connected_only"}` and `heartbeat_force_connected=True`.
    ///
    /// `cycles` is in K20 instruction cycles (Tcy).  Each chunk
    /// advances `CHUNK_TCY = 2_000_000 K20-Tcy` (matches gpsim's
    /// `warmup_chunk = max(chunk_cycles, 2_000_000)`).  The hook
    /// is gated on `display_entered` (mirrors gpsim's
    /// `_heartbeat_active` gate around `_heartbeat_pre_step`):
    /// during the pre-DISPLAY phase the hook is NOT applied, so
    /// the firmware's own bit1 transition can be observed
    /// reliably by the next pre-chunk read; if the hook were
    /// applied unconditionally before DISPLAY entry, its bit1
    /// OR would leak into the next chunk's pre-hook read and
    /// trip `display_entered` early (codex MEDIUM-2 from review
    /// of ac6eb09: "cross-iteration stale-bit risk").  Once the
    /// firmware itself enters DISPLAY mode:
    ///   * The 5-frame BF burst stops (avoids ring-overflow on
    ///     long warmups).
    ///   * The WAITING-screen sentinels at 0x0B8/0x0B9/0x0A7/
    ///     0x0A1 are seeded once to plausible non-0x80 values.
    ///   * The force-connected hook starts firing every chunk.
    ///
    /// Implicitly calls `enable_force_connected()` so post-
    /// warmup `step()` calls keep applying the hook even after
    /// `warmup_force_connected` returns.
    fn warmup_force_connected(&mut self, cycles: u64) {
        self.force_connected = true;
        const WARMUP_BF_BURST: [u8; 15] = [
            0xBF, 0x05, 0x33, // volume = 0x33 (-45 dB)
            0xBF, 0x07, 0x60, // input = 0x60 (Auto)
            0xBF, 0x03, 0x01, // mute = off, sets CONNECTED
            0xBF, 0x06, 0x00, // source config
            0xBF, 0x1D, 0x00, // display/timeout
        ];
        const CHUNK_TCY: u64 = 2_000_000;
        let factor = self.tcy_factor();
        let mut remaining = cycles;
        let mut display_entered = false;
        while remaining > 0 {
            // Sample DISPLAY mode at the start of each chunk.
            // Pre-DISPLAY: the hook hasn't run, so any bit1=1
            // we observe came from the firmware itself (BF/03/01
            // RX → CONNECTED).  Post-DISPLAY: the hook is
            // already firing each chunk, so bit1 is always 1;
            // the latched `display_entered` flag prevents this
            // from re-running the seeding block.
            let in_display = {
                let v = self.inner.cores[self.i_ctl]
                    .memory
                    .read_raw(dlcp_sim::memory::Address::from_raw(0x01F));
                v & 0x02 != 0
            };
            if in_display && !display_entered {
                display_entered = true;
                let mem = &mut self.inner.cores[self.i_ctl].memory;
                mem.write_raw(dlcp_sim::memory::Address::from_raw(0x0B8), 0x00); // input_sel
                mem.write_raw(dlcp_sim::memory::Address::from_raw(0x0B9), 0x33); // volume
                mem.write_raw(dlcp_sim::memory::Address::from_raw(0x0A7), 0x01); // cmd1d
                mem.write_raw(dlcp_sim::memory::Address::from_raw(0x0A1), 0x01); // unit_count
            }
            // The force-connected hook is gated on
            // `display_entered` -- mirror of gpsim's
            // `_heartbeat_pre_step`'s `if self._heartbeat_active`
            // guard.  Pre-DISPLAY, the firmware's natural bit1
            // transition needs to be observable; post-DISPLAY,
            // the hook keeps CONNECTED + event-exit asserted.
            if display_entered {
                self.apply_force_connected_hook();
            }
            // Mirror of `control_gpsim.py::warmup` -- inject the
            // 5-frame BF status burst ONLY while the firmware is
            // still pre-DISPLAY.  Once DISPLAY mode is observed,
            // stop injecting so the RX ring doesn't accumulate
            // unread BF replies that would overflow on a long
            // warmup.
            if !display_entered {
                self.inject_control_rx_bytes_inner(&WARMUP_BF_BURST);
            }
            let advance = CHUNK_TCY.min(remaining);
            self.inner.step_ticks(advance * factor);
            remaining -= advance;
        }
    }
}

impl Chain {
    /// Internal helper: push `bytes` (typically 3 for one
    /// chain frame) into CONTROL's RX ring buffer.  Returns
    /// false if the ring would overflow.  V1.6b/V1.71 ring
    /// layout: `rx_ring_base = 0x066`,
    /// `rx_ring_rd = 0x098`, `rx_ring_wr = 0x099`, depth
    /// = 48 bytes.
    ///
    /// Wrap-aware used = (wr + DEPTH - rd) mod DEPTH (NOT
    /// `wr.wrapping_sub(rd) mod DEPTH` -- the latter agrees
    /// with Python's `(wr - rd) % DEPTH` only when wr >= rd
    /// and silently corrupts the count when the ring has
    /// wrapped past rd.  Codex review of 46d7163 (HIGH)
    /// caught the regression: e.g. rd=10/wr=9 should yield
    /// used=47/free=0, but the prior expression yielded
    /// used=15/free=32, which would let a near-full wrapped
    /// ring accept new bytes that overwrite unread data.)
    ///
    /// `wr` and `rd` are read as u8 from memory but
    /// normalized to `[0, DEPTH)` BEFORE the subtraction
    /// (codex review of 3a3afb9 (LOW): without normalization,
    /// out-of-range register values like `rd=0xFF, wr=0` --
    /// possible during pre-warmup uninitialised RAM windows
    /// or pathological injections -- can underflow `wr +
    /// DEPTH - rd` and diverge from Python's arbitrary-
    /// precision `(wr - rd) % DEPTH`.  After normalization,
    /// both indices are in `[0, DEPTH)` and `wr + DEPTH >
    /// rd` always, so the subtraction is well-defined.)
    fn inject_rx_bytes_inner(&mut self, bytes: &[u8]) -> bool {
        const RX_RING_BASE: u16 = 0x066;
        const RX_RING_RD: u16 = 0x098;
        const RX_RING_WR: u16 = 0x099;
        const RX_RING_DEPTH: u16 = 48;

        let mem = &mut self.inner.cores[self.i_ctl].memory;
        let rd =
            (mem.read_raw(dlcp_sim::memory::Address::from_raw(RX_RING_RD)) as u16) % RX_RING_DEPTH;
        let mut wr =
            (mem.read_raw(dlcp_sim::memory::Address::from_raw(RX_RING_WR)) as u16) % RX_RING_DEPTH;
        let used = (wr + RX_RING_DEPTH - rd) % RX_RING_DEPTH;
        let free = (RX_RING_DEPTH - 1).saturating_sub(used);
        if (bytes.len() as u16) > free {
            return false;
        }
        for &byte in bytes {
            let addr = RX_RING_BASE + wr;
            mem.write_raw(dlcp_sim::memory::Address::from_raw(addr), byte);
            wr = (wr + 1) % RX_RING_DEPTH;
        }
        mem.write_raw(dlcp_sim::memory::Address::from_raw(RX_RING_WR), wr as u8);
        true
    }
}

#[pymodule]
fn dlcp_sim_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_class::<Chain>()?;
    Ok(())
}
