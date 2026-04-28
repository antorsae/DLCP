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
}

/// One CONTROL chunk in the gpsim harness is 200_000 Tcy
/// (`SingleMainChainHarness::__init__` ->
/// `control_chunk_cycles=200_000`); the K20 runs at
/// 16 universal ticks per Tcy, so each chunk advances
/// 3_200_000 universal ticks.  `run_until_connected(limit)`
/// matches gpsim's chunk-count contract by stepping
/// `limit * V17_CHUNK_TICKS` total ticks (broken into
/// per-chunk sub-steps so the connection check has the
/// same granularity as the gpsim path).
const V17_CHUNK_TICKS: u64 = 200_000 * 16;

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

    /// Step the chain in `V17_CHUNK_TICKS` chunks (mirroring
    /// gpsim's 200K-Tcy / 3.2M-tick chunk cadence) up to
    /// `limit` chunks, returning early as soon as the
    /// chain has reached the steady-state CONNECTED Volume
    /// display.  Returns the number of chunks actually
    /// consumed (== `limit` if the predicate never fired).
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
        for chunk in 0..limit {
            self.inner.step_ticks(V17_CHUNK_TICKS);
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

    /// Step in `V17_CHUNK_TICKS` chunks (mirroring gpsim's
    /// 200K-Tcy / 3.2M-tick chunk cadence) up to `limit`
    /// chunks, returning early as soon as `is_waiting()` is
    /// true.  Returns the number of chunks actually consumed
    /// (== `limit` if the predicate never fired).  Mirror of
    /// `chain_gpsim.py::SingleMainChainHarness::run_until_waiting`.
    /// Used by the V1.7 blackout/wake migration test to
    /// verify CONTROL falls back to the WAITING screen after
    /// a wake-while-blacked-out.
    fn run_until_waiting(&mut self, limit: usize) -> usize {
        for chunk in 0..limit {
            self.inner.step_ticks(V17_CHUNK_TICKS);
            if self.is_waiting() {
                return chunk + 1;
            }
        }
        limit
    }

    /// Step the chain by `n_chunks` chunks of
    /// `V17_CHUNK_TICKS` ticks each (no early-exit
    /// predicate).  Mirror of
    /// `chain_gpsim.py::SingleMainChainHarness::step_many`.
    /// Used by the V1.7 blackout/wake migration test to
    /// give the firmware time to settle into standby (Zzz)
    /// after the STBY-press, before re-pressing to wake.
    fn step_many(&mut self, n_chunks: usize) {
        for _ in 0..n_chunks {
            self.inner.step_ticks(V17_CHUNK_TICKS);
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
}

#[pymodule]
fn dlcp_sim_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_class::<Chain>()?;
    Ok(())
}
