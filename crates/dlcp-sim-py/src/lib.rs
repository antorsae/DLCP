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

use pyo3::prelude::*;
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use std::path::PathBuf;

use dlcp_sim::chain::Chain as RustChain;
use dlcp_sim::core::Core;
use dlcp_sim::hex::HexImage;
use dlcp_sim::lcd::Hd44780;
use dlcp_sim::memory::Variant;
use dlcp_sim::peripherals::src4382::Src4382;
use dlcp_sim::peripherals::tas3108::Tas3108;
use dlcp_sim::pinnet::{default_rx_pin, default_tx_pin, PortLetter};
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
    let mut core = Core::new(Variant::Pic18F2455);
    core.flash_mut()
        .copy_from_slice(&*build_seeded_main_flash(v3_app, v23_seed));
    for (addr, &byte) in v23_seed.eeprom.iter().enumerate() {
        core.peripherals.eeprom.set_byte(addr as u8, byte);
    }
    core
}

/// Build a CONTROL (K20) core from a V1.71 hex.  Mirror
/// of `multicore_parity.rs:227::build_core_from_hex` for
/// the K20 path: copy flash, seed EEPROM byte-for-byte
/// (including 0xFF "erased" bytes -- firmware
/// distinguishes 0xFF-erased from 0x00-default at runtime
/// via "uninitialized" sentinel checks).  Config / user_id
/// stay at their `Core::new` defaults (all-zero CONFIG, all-
/// 0xFF user_id) -- matching what the existing test
/// harness does and what the deployed DLCP firmware
/// expects (CONFIG4L=0x80, see `core.rs:99-107` for
/// rationale).
fn build_v171_control_core(v171: &HexImage) -> Core {
    let mut core = Core::new(Variant::Pic18F25K20);
    core.flash_mut().copy_from_slice(&*v171.flash);
    for (addr, &byte) in v171.eeprom.iter().enumerate() {
        core.peripherals.eeprom.set_byte(addr as u8, byte);
    }
    core
}

/// Build a stock V2.3 MAIN core from V2.3-combined.  Unlike
/// V3.x, V2.3-combined ships the FULL silicon image (boot
/// block + V2.3 app + EEPROM + preset tables) -- no merge
/// or `bake_goto` trampolines needed.
fn build_stock_v23_main_core(v23_combined: &HexImage) -> Core {
    let mut core = Core::new(Variant::Pic18F2455);
    core.flash_mut().copy_from_slice(&*v23_combined.flash);
    for (addr, &byte) in v23_combined.eeprom.iter().enumerate() {
        core.peripherals.eeprom.set_byte(addr as u8, byte);
    }
    core
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

/// Build a 2-core chain (1 CONTROL/K20 + 1 MAIN/2455) with
/// bidirectional UART, TAS3108 DSP slave on MAIN, HD44780
/// LCD slave on CONTROL.  POR-reset, initial steps scheduled
/// at tick 0.  PORTA/PORTC seeded to 0xFF (buttons released);
/// AN0 ADC sample seeded to 0x0300 (mid-rail mains-detect).
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
    // reaches_volume_screen` (lines ~5092-5097) and the
    // V1.71+V3.1 LCD parity test seed (ibid lines ~4992-4997).
    chain.cores[i_ctl]
        .memory
        .write_raw(dlcp_sim::memory::Address::from_raw(0xF80), 0xFF); // PORTA
    chain.cores[i_ctl]
        .memory
        .write_raw(dlcp_sim::memory::Address::from_raw(0xF82), 0xFF); // PORTC

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
fn build_v17_control_only_chain(
    control_hex_path: PathBuf,
) -> Result<V17SingleMainHandle, String> {
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
    chain.cores[i_ctl]
        .memory
        .write_raw(dlcp_sim::memory::Address::from_raw(0xF80), 0xFF); // PORTA
    chain.cores[i_ctl]
        .memory
        .write_raw(dlcp_sim::memory::Address::from_raw(0xF82), 0xFF); // PORTC

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

    chain.cores[i_ctl]
        .memory
        .write_raw(dlcp_sim::memory::Address::from_raw(0xF80), 0xFF); // PORTA
    chain.cores[i_ctl]
        .memory
        .write_raw(dlcp_sim::memory::Address::from_raw(0xF82), 0xFF); // PORTC

    Ok(V17SingleMainHandle {
        chain,
        i_ctl,
        i_main,
        i_lcd,
        i_dsp,
    })
}

fn build_v171_v32_chain() -> Result<V171V32ChainHandle, String> {
    let v171 = HexImage::from_hex_path(v171_control_hex_path())
        .map_err(|e| format!("V1.71 hex parse: {e:?}"))?;
    let v32 = HexImage::from_hex_path(v32_main_hex_path())
        .map_err(|e| format!("V3.2 hex parse: {e:?}"))?;
    let v23 = HexImage::from_hex_path(v23_main_combined_hex_path())
        .map_err(|e| format!("V2.3-combined hex parse: {e:?}"))?;

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
    tx_capture_main0: usize,
    /// When true, every step() / warmup_force_connected()
    /// chunk applies the per-step "force CONNECTED" hook to
    /// CONTROL: ORs bits 1+3 into 0x01F (CONNECTED + event-
    /// exit) and resets the idle timer at 0x09D/0x09E.
    /// Mirror of gpsim's
    /// `GpsimControlHarness(heartbeat_force_connected=True)`
    /// behavior.  Used by CONTROL-only chains that must keep
    /// the firmware in DISPLAY mode without a real MAIN peer.
    /// Default false; enable via `enable_force_connected()`.
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
        mem.write_raw(
            dlcp_sim::memory::Address::from_raw(0x01F),
            cur | 0x0A,
        );
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
        let rd = mem.read_raw(dlcp_sim::memory::Address::from_raw(RX_RD)) as u16
            % RX_DEPTH;
        let mut wr = mem.read_raw(dlcp_sim::memory::Address::from_raw(RX_WR)) as u16
            % RX_DEPTH;
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
    fn from_v171_v32() -> PyResult<Self> {
        let handle = build_v171_v32_chain()
            .map_err(|e| PyRuntimeError::new_err(format!("from_v171_v32: {e}")))?;
        Ok(Self {
            inner: handle.chain,
            i_ctl: handle.i_ctl,
            i_main0: handle.i_main0,
            i_main1: handle.i_main1,
            i_lcd: handle.i_lcd,
            tx_capture_main0: 0,
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
        Self::from_v17_chain(
            v16b_control_hex_path().to_string_lossy().into_owned(),
            None,
        )
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
            force_connected: false,
        })
    }

    /// Convenience: V1.71 CONTROL + V3.1 MAIN single-MAIN
    /// chain.  Mirror of
    /// `tests/sim/test_v171_v31_chain.py::_new_pair`.
    /// Uses the canonical V3.1 release hex (app-only)
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
        let handle = build_v3x_main_only_chain(
            PathBuf::from(v3x_main_hex_path),
            v23_seed,
        )
        .map_err(|e| PyRuntimeError::new_err(format!("from_v3x_main_only: {e}")))?;
        Ok(Self {
            inner: handle.chain,
            i_ctl: handle.i_ctl,
            i_main0: handle.i_main,
            i_main1: handle.i_main,
            i_lcd: handle.i_lcd,
            tx_capture_main0: 0,
            force_connected: false,
        })
    }

    /// Convenience: V3.1 MAIN-only chain (canonical V3.1
    /// release hex + V2.3-combined seed).
    #[staticmethod]
    fn from_v31_main_only() -> PyResult<Self> {
        Self::from_v3x_main_only(
            v31_main_hex_path().to_string_lossy().into_owned(),
            None,
        )
    }

    /// Convenience: V3.2 MAIN-only chain (canonical V3.2
    /// release hex + V2.3-combined seed).
    #[staticmethod]
    fn from_v32_main_only() -> PyResult<Self> {
        Self::from_v3x_main_only(
            v32_main_hex_path().to_string_lossy().into_owned(),
            None,
        )
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
    fn from_v17_chain(
        control_hex_path: String,
        main_hex_path: Option<String>,
    ) -> PyResult<Self> {
        let main_path = main_hex_path
            .map(PathBuf::from)
            .unwrap_or_else(v23_main_combined_hex_path);
        let handle = build_v17_chain_single_main(
            PathBuf::from(control_hex_path),
            main_path,
        )
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
        let (port, bit) = panel_button_pin(key)
            .map_err(PyValueError::new_err)?;
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
    fn set_mssp_stop_fault(
        &mut self,
        stop_busy_cycles: u32,
        stop_busy_count: i64,
    ) {
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
            dlcp_sim::memory::Address::from_raw(
                dlcp_sim::peripherals::mssp::SSPCON2_ADDR,
            ),
            0,
        );
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
    fn inject_decoded_ir_event(
        &mut self,
        addr: u8,
        cmd: u8,
        clear_debounce: bool,
    ) {
        let mem = &mut self.inner.cores[self.i_ctl].memory;
        if clear_debounce {
            mem.write_raw(dlcp_sim::memory::Address::from_raw(0x01B), 0x00);
            mem.write_raw(dlcp_sim::memory::Address::from_raw(0x01C), 0x00);
        }
        mem.write_raw(dlcp_sim::memory::Address::from_raw(0x01D), cmd);
        mem.write_raw(dlcp_sim::memory::Address::from_raw(0x01E), addr);
        // Clear control_flags.IR_ARMED (bit 0 of 0x01F).
        let flags = mem.read_raw(dlcp_sim::memory::Address::from_raw(0x01F));
        mem.write_raw(
            dlcp_sim::memory::Address::from_raw(0x01F),
            flags & !0x01,
        );
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
        bytes
            .chunks_exact(3)
            .map(|c| (c[0], c[1], c[2]))
            .collect()
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
        let result = main_records[self.tx_capture_main0..].to_vec();
        self.tx_capture_main0 = main_records.len();
        result
    }

    /// Reset the TX capture pointer to the current end of
    /// MAIN0's recorded TX history -- subsequent
    /// `tx_record_since_last_capture` calls only see bytes
    /// pushed AFTER this call.  Use when the test wants to
    /// drop pre-stimulus bytes (boot-time TX, prior query
    /// responses) before injecting the next stimulus.
    fn mark_tx_capture_point(&mut self) {
        let main0 = self.i_main0;
        self.tx_capture_main0 = self
            .inner
            .uart_tx_history
            .iter()
            .filter(|r| r.src_core == main0)
            .count();
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
    /// AND every chunk inside `warmup_force_connected()`
    /// applies the pokes documented on
    /// `apply_force_connected_hook` (OR 0x0A into 0x01F, reset
    /// 0x09D/0x09E to 0xFF) BEFORE advancing time.
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
    /// DISPLAY transition by repeatedly applying the
    /// force-connected hook AND injecting a synthetic BF status
    /// burst (5-frame `BF/05/33 BF/07/60 BF/03/01 BF/06/00
    /// BF/1D/00`) until DISPLAY mode is detected (0x01F bit 1
    /// set), or the cycle budget is exhausted.  Mirror of
    /// `GpsimControlHarness.warmup` when the harness was
    /// constructed with `heartbeat_rx_mode in {"full",
    /// "connected_only"}` and `heartbeat_force_connected=True`.
    ///
    /// `cycles` is in K20 instruction cycles (Tcy).  Each
    /// chunk advances `chunk_tcy = 200_000 K20-Tcy` (gpsim's
    /// default `chunk_cycles`) so the hook fires regularly
    /// during boot.  Once DISPLAY mode is detected, the
    /// 5-frame BF burst stops (to avoid ring-overflow) but
    /// the per-chunk force-connected hook continues to keep
    /// CONNECTED + event-exit set.  This is enough to drive
    /// the IR / button / preset-action tests in the V1.5b /
    /// V1.6b port-compatibility suite that need DISPLAY
    /// mode but no real MAIN peer.  Implicitly also calls
    /// `enable_force_connected()` so post-warmup `step()` calls
    /// keep applying the hook.
    fn warmup_force_connected(&mut self, cycles: u64) {
        self.force_connected = true;
        const WARMUP_BF_BURST: [u8; 15] = [
            0xBF, 0x05, 0x33, // volume = 0x33 (-45 dB)
            0xBF, 0x07, 0x60, // input = 0x60 (Auto)
            0xBF, 0x03, 0x01, // mute = off, sets CONNECTED
            0xBF, 0x06, 0x00, // source config
            0xBF, 0x1D, 0x00, // display/timeout
        ];
        // 2 M Tcy chunks during warmup (matches gpsim's
        // `warmup_chunk = max(chunk_cycles, 2_000_000)`).  At
        // 31_250 baud the ring drains ~2602 bytes per 2 M Tcy
        // chunk, far more than the 15-byte burst, so the burst
        // never overflows.
        const CHUNK_TCY: u64 = 2_000_000;
        let factor = self.tcy_factor();
        let mut remaining = cycles;
        let mut display_entered = false;
        while remaining > 0 {
            self.apply_force_connected_hook();
            // Inject the BF status burst every chunk so the
            // firmware's MAIN-discovery / sentinel-update logic
            // keeps making progress.  Once we observe DISPLAY
            // mode (0x01F.bit1 set) for the first time, force
            // the WAITING-screen sentinels to plausible non-
            // 0x80 values so the firmware's subsequent
            // "WAITING entered?" checks succeed (mirror of
            // `control_gpsim.py::_update_waiting_detection`'s
            // post-detection seeding).
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
            self.inject_control_rx_bytes_inner(&WARMUP_BF_BURST);
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
        let rd = (mem.read_raw(dlcp_sim::memory::Address::from_raw(RX_RING_RD)) as u16)
            % RX_RING_DEPTH;
        let mut wr = (mem.read_raw(dlcp_sim::memory::Address::from_raw(RX_RING_WR)) as u16)
            % RX_RING_DEPTH;
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
        mem.write_raw(
            dlcp_sim::memory::Address::from_raw(RX_RING_WR),
            wr as u8,
        );
        true
    }
}

#[pymodule]
fn dlcp_sim_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_class::<Chain>()?;
    Ok(())
}
