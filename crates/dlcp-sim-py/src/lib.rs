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
use pyo3::exceptions::PyRuntimeError;
use std::path::PathBuf;

use dlcp_sim::chain::Chain as RustChain;
use dlcp_sim::core::Core;
use dlcp_sim::hex::HexImage;
use dlcp_sim::lcd::Hd44780;
use dlcp_sim::memory::Variant;
use dlcp_sim::peripherals::tas3108::Tas3108;
use dlcp_sim::pinnet::{default_rx_pin, default_tx_pin};
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
/// `dlcp_sim::chain::Chain` plus the bookkeeping
/// indices that `from_v171_v32()` populated (so methods
/// like `lcd_lines()` know which LCD slave to read from).
#[pyclass]
struct Chain {
    inner: RustChain,
    i_ctl: usize,
    i_main0: usize,
    i_main1: usize,
    i_lcd: usize,
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
        })
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

    /// Index of MAIN0.
    #[getter]
    fn main0(&self) -> usize {
        self.i_main0
    }

    /// Index of MAIN1.
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
}

#[pymodule]
fn dlcp_sim_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_class::<Chain>()?;
    Ok(())
}
