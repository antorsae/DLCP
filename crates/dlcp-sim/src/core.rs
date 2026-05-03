//! Single PIC18 core: program memory, data memory, ALU registers,
//! and the cycle counter.  P1.1 only lays the storage; the
//! instruction interpreter (P1.2-P1.4), hardware stack (P1.5),
//! reset path (P1.6), and config-bit parser (P1.7) wire behaviour
//! into this struct.
//!
//! ## What lives here vs. elsewhere
//!
//! * `Core` owns the bytes — flash, RAM, ALU regs, cycle counter.
//! * The ALU registers (`W`, `STATUS`, `BSR`, `FSRn`, `STKPTR`,
//!   `PCL/PCH/PCLATH/PCLATU`) are PIC18 SFRs in real silicon, so
//!   they live inside the [`crate::memory::Memory`] backing array
//!   too — but the interpreter accesses them through dedicated
//!   helpers since they're touched on every instruction.  P1.2
//!   adds those helpers; P1.1 just allocates the storage.
//! * Peripheral side-effects on SFR writes (BAUDCON.BRG16
//!   reconfiguring the baud generator, EECON1.WR triggering an
//!   EEPROM write, etc.) live in `crate::peripherals::*` from P2
//!   onward.  `Core` is unaware of them; the dispatcher in P2
//!   wraps `Memory::write_raw` to fan out to peripherals.
//!
//! ## Cycle counter semantics
//!
//! `cycles` counts **instruction cycles** (Tcy), not the universal
//! 48 MHz tick that the multi-core scheduler uses in P3.  A core
//! running at 16 MHz Fosc has Tcy = 250 ns and increments `cycles`
//! by 1 per single-Tcy instruction (most ops), 2 per multi-Tcy
//! instruction (CALL, GOTO, table read, etc.).  P3's `Chain`
//! converts Tcy → universal ticks via `ticks_per_tcy`.

#![allow(dead_code, reason = "P1.1 skeleton; behaviour wired in P1.2+")]

use crate::config::Config;
use crate::hex::HexImage;
use crate::memory::{Address, Memory, Variant};
use crate::peripherals::{irq, Peripherals};

/// Default reset vector for both supported PIC18 variants.
/// Confirmed to be 0x0000 in DS39632E §5.2 and DS41303G §5.2
/// (PIC18 ISA architectural constant, same for every PIC18 chip).
pub const RESET_VECTOR: u32 = 0x0000;

/// One-deep fast register shadow per DS39632E §5.5.3 /
/// DS40001303H §5.5.3.  Saved on `CALL FAST` / hardware IRQ
/// entry (in IPEN=1 mode); restored on `RETURN FAST` /
/// `RETFIE FAST`.  When IPEN=0 (compatibility) the hardware
/// IRQ entry does NOT push the shadow, but `CALL FAST` and
/// `RETFIE FAST` still use it (the firmware can rely on the
/// shadow to save W/STATUS/BSR around an explicit `CALL
/// FAST main_isr_dispatch` even with IPEN=0 -- this is V3.1's
/// idiom).
#[derive(Copy, Clone, Debug, Default, PartialEq, Eq)]
pub struct FastRegs {
    pub wreg: u8,
    pub status: u8,
    pub bsr: u8,
}

#[derive(Copy, Clone, Debug, Eq, PartialEq)]
pub enum RunState {
    Running,
    Sleep,
    Idle,
}

#[derive(Copy, Clone, Debug, Eq, PartialEq)]
pub enum IrqContext {
    Compatibility,
    High,
    Low,
}

/// Deterministic nominal WDT base period in instruction cycles.
/// Datasheet anchor: DS40001303H §23.2 and DS39632E §25.2
/// define a nominal 4 ms WDT period before CONFIG2H.WDTPS.
/// The simulator uses the MAIN 4 MIPS scale (`4 ms = 16000 Tcy`)
/// as the variant-independent nominal base; WDTPS applies as
/// `1 << WDTPS`.
pub const WDT_BASE_TCY: u64 = 16_000;
const WDTCON_ADDR: u16 = 0xFD1;
const RCON_ADDR: u16 = 0xFD0;
const RCON_TO: u8 = 1 << 3;

/// One PIC18 core: program memory + data memory + cycle counter
/// + peripheral state machines.  P1.1 only allocates storage.
/// Reset, instruction fetch, decode, and execute come online in
/// subsequent sub-tasks; P2 hangs peripheral state off this
/// struct via the `peripherals` field.
#[derive(Clone)]
pub struct Core {
    variant: Variant,
    /// Program memory (flash).  Byte-addressed; PIC18 instructions
    /// are 16-bit (2 bytes) at even addresses, but the storage
    /// itself is per-byte so the table-read instructions work
    /// uniformly.  Sized via [`Variant::program_memory_bytes`].
    flash: Box<[u8]>,
    /// Data memory: banked RAM + SFR window.  See [`Memory`].
    pub memory: Memory,
    /// Peripheral state.  Mutated through two paths:
    /// `Core::advance_cycles` ticks each peripheral by the
    /// elapsed Tcy after every instruction, and the executor's
    /// `write_addr_masked` calls `Peripherals::on_sfr_write`
    /// after every SW-driven SFR write so peripherals can react
    /// to mode changes / FIFO pushes.
    pub peripherals: Peripherals,
    /// Program counter.  PIC18 PC is 21 bits (the upper byte
    /// `PCLATU` is only 5 bits wide) AND byte-addressed but
    /// architecturally word-aligned: PCL bit 0 is hard-wired to
    /// 0 in silicon (DS39632E §5.5.1, DS41303G §5.5.1).  We
    /// widen to `u32` for arithmetic convenience and rely on
    /// [`Core::set_pc`] to keep `pc & !0x001F_FFFE == 0` —
    /// upper 11 bits clear AND bit 0 clear — at all times.
    pc: u32,
    /// Total Tcy elapsed since the last reset.  Plain `u64` is
    /// enough for >250 years at 4 MIPS, far beyond any test run.
    cycles: u64,
    /// Fast register shadow (DS39632E §5.5.3): 1-deep
    /// silicon-private stack of W/STATUS/BSR.  Pushed on
    /// `CALL FAST` (s=1) and on hardware IRQ entry when
    /// IPEN=1; popped on `RETURN FAST` and `RETFIE FAST`.
    /// Without this, V3.1's ISR pattern (`CALL FAST
    /// main_isr_dispatch` + `RETFIE 1`) corrupts main-line
    /// W/STATUS/BSR.  Task #15.
    pub fast_shadow: FastRegs,
    /// Parsed CONFIG-region bits.  Consumers: STVREN gating
    /// in `exec::step`'s stack-fault path (task #16); future
    /// peripheral fidelity for FOSC / WDT / IESO.  Default
    /// is all-zero CONFIG bytes -- STVREN=0 (latch-only),
    /// matching the deployed DLCP firmware's CONFIG4L=0x80.
    /// Test/loader code that wants strict silicon defaults
    /// (un-programmed = all-1s = STVREN=1) writes the field
    /// explicitly.
    pub config: Config,
    /// User-ID region bytes (DS39632E §6.7 / DS40001303H §3.1):
    /// 8 bytes at TBLPTR=0x200000..0x200007, application-
    /// defined.  TBLRD with TBLPTR pointing here returns
    /// these bytes; TBLWT with EECON1.CFGS=1 + EECON1.WR=1
    /// commits the holding latch to this window (the WR
    /// commit itself is a P2 EEPROM/flash-write peripheral
    /// concern -- this struct just owns the storage).
    /// Default `0xFF` matches the un-programmed silicon
    /// state.  The field is `pub`, so hex loaders populate
    /// it via direct assignment (`core.user_id = ...`),
    /// mirroring the `core.config = ...` pattern.
    /// Task #17.
    pub user_id: [u8; 8],
    /// TBLWT staging buffer (DS39632E §6.5.2 / DS40001303H
    /// §6.5.2).  PIC18 self-programming loads bytes into a
    /// silicon-internal holding register via TBLWT, then
    /// firmware sets EECON1.WR (with the EE unlock sequence)
    /// to commit the holding-buffer block to flash / config
    /// / user-id memory.  Both supported variants share the
    /// 32-byte write-block size:
    /// 2455 -- DS39632E §6.4 ("blocks of 32 bytes at a
    /// time"; 32 holding registers selected by
    /// TBLPTR<4:0>).
    /// 25K20 -- DS40001303H Tbl 6-1 (PIC18F25K20 row =
    /// 32-byte write block, 64-byte erase block; the
    /// 16-byte row applies to PIC18F23K20 / 43K20 only).
    /// TBLWT writes the byte at
    /// `tblwt_holding[TBLPTR & 0x1F]`.  The commit-to-flash
    /// path is the future P2 flash-write peripheral's
    /// concern; this struct just owns the staging.  Default
    /// all-`0xFF` (silicon erased).  Task #17.
    pub tblwt_holding: [u8; TBLWT_HOLDING_SIZE],
    /// MCLR-held-low gate.  When `true`, `Chain::execute_core_step`
    /// short-circuits before the instruction body runs -- the core's
    /// PC, cycles, and peripheral state are frozen, but scheduling
    /// for other cores continues.  Models the silicon behaviour of a
    /// PIC18 with its MCLR pin held LOW: the CPU is in reset, drawing
    /// no clocks, while the rest of the chain runs.  Used by P3.8b's
    /// "MAIN1 never wakes" probe to model the asymmetric-wake field
    /// bug filed as task #45 without inventing an artificial
    /// `pause_core` debug hook.  Default `false` (core runs).
    /// Task #47 (P3.8b-prereq).
    pub mclr_held: bool,
    pub run_state: RunState,
    irq_context_stack: [Option<IrqContext>; 8],
    irq_context_depth: usize,
    wdt_counter_tcy: u64,
    wdt_timeout_pending: bool,
    /// Optional cycle-level probe used by research scaffolding
    /// (e.g. P3.6b research step 2, task #62) to count exact
    /// per-instruction PC entries to a labelled flash range AND
    /// log every transition of a watched RAM cell.  Default
    /// `None` -- when `None`, the only cost is two `Option`
    /// discriminant checks per step (one in `exec::step` before
    /// instruction fetch for the PC range counter, one in
    /// `Chain::execute_core_step` after the step for the RAM
    /// watch).  When `Some(_)`:
    ///   * `exec::step` increments PC range hit counters AFTER
    ///     the IRQ-dispatch early-return, so only PCs of
    ///     instructions that will actually execute are counted.
    ///     Codex MEDIUM from 92fe865.
    ///   * `Chain::execute_core_step` walks watched RAM cells
    ///     after the step returns and pushes a transition entry
    ///     when the post-step value differs from `last_value`.
    /// Test-only field; production chains should leave this
    /// `None`.
    pub cycle_probe: Option<CycleProbe>,
}

/// Per-instruction probe -- see `Core::cycle_probe`.  Holds an
/// arbitrary number of labelled PC ranges (each with a hit
/// counter) and watched RAM cells (each with a last-value
/// cache and a transition log keyed by `Chain::current_tick`).
///
/// Construct via `CycleProbe::new()` then `add_pc_range(..)`
/// / `add_watched_ram(..)` to register the things you want
/// monitored before attaching to `Core::cycle_probe`.
#[derive(Clone, Default, Debug)]
pub struct CycleProbe {
    /// PC ranges to count instruction entries to.  Each entry
    /// is `(start_inclusive, end_exclusive, label, hit_count)`.
    pub pc_ranges: Vec<PcRangeProbe>,
    /// RAM cells to watch.  Each entry tracks `(addr, label,
    /// last_value, transitions)`.
    pub watched_ram: Vec<WatchedRamProbe>,
}

#[derive(Clone, Debug)]
pub struct PcRangeProbe {
    /// Inclusive start of the flash byte range (PC values).
    pub start: u16,
    /// Exclusive end of the flash byte range.
    pub end: u16,
    /// Human-readable label printed in probe summaries
    /// (e.g. `"v171_bf2x_case_check"`).
    pub label: &'static str,
    /// Count of instructions ACTUALLY EXECUTED whose
    /// pre-fetch PC fell in `[start, end)`.  Incremented
    /// inside `exec::step` AFTER the IRQ-dispatch
    /// early-return, so a step that vectors to an ISR
    /// (rather than executing the instruction at PC) does
    /// NOT increment -- the same PC counts on the next
    /// step that actually fetches+executes it.  Codex
    /// MEDIUM from 92fe865.
    pub hit_count: u64,
    /// Total Tcy accumulated for instructions whose
    /// pre-fetch PC fell in `[start, end)`.  Updated
    /// inside `exec::step` AFTER instruction execution by
    /// adding the post-step `Core::cycles()` minus the
    /// pre-step `Core::cycles()`.  P3.6b research step 6
    /// (task #67): together with `hit_count`, this lets
    /// the probe attribute Tcy budgets to specific
    /// subroutines / dispatch branches without touching
    /// the firmware or the sampling cadence.
    pub total_cycles: u64,
}

#[derive(Clone, Debug)]
pub struct WatchedRamProbe {
    /// Physical RAM address (bank-flattened) to watch.
    pub addr: u16,
    /// Human-readable label.
    pub label: &'static str,
    /// Last observed value.  Initialized to whatever was in
    /// the RAM cell at the moment the probe was attached.
    pub last_value: u8,
    /// Transition log: `(tick, new_value)` for every observed
    /// change.  Pushed by `Chain::execute_core_step` AFTER
    /// each `exec::step` call when the post-step value
    /// differs from `last_value`.
    pub transitions: Vec<(u64, u8)>,
    /// Optional intervention: when the watched cell
    /// transitions to a value in `[trigger_min, trigger_max]`
    /// (inclusive), write `trigger_target_value` to
    /// `trigger_target_addr` and increment `trigger_fire_count`.
    /// Used by P3.6b research step 4 (task #65) to validate
    /// the parser-stall watchdog hypothesis: when
    /// `rx_parsed_cmd` (0x02F) transitions to a BF/2N cmd
    /// (0x21..=0x2B), reset `v171_rx_frame_gap_timeout`
    /// (0x0AC) to 0x01 so the watchdog's 8-step count-up
    /// won't expire before the data byte arrives.  None means
    /// "transition log only, no intervention".
    pub trigger: Option<RamTransitionTrigger>,
}

/// Minimal transition-driven memory write -- see
/// `WatchedRamProbe::trigger`.  When the parent watched cell
/// transitions to a value in `[match_min, match_max]`
/// (inclusive), the chain writes `target_value` to
/// `target_addr` and increments `fire_count`.  Static fields
/// (no closures / function pointers) so the struct stays
/// `Clone + Debug` and probes remain easy to inspect.
#[derive(Clone, Debug)]
pub struct RamTransitionTrigger {
    /// Inclusive lower bound for the new value to match.
    pub match_min: u8,
    /// Inclusive upper bound for the new value to match.
    pub match_max: u8,
    /// Physical RAM address (bank-flattened) to write.
    pub target_addr: u16,
    /// Value to write to `target_addr`.
    pub target_value: u8,
    /// Count of times this trigger has fired -- read at
    /// probe-dump time to confirm the intervention took
    /// effect.
    pub fire_count: u64,
}

impl CycleProbe {
    /// Construct an empty probe with no PC ranges and no
    /// watched RAM cells.  Add registrations before
    /// attaching to `Core::cycle_probe`.
    pub fn new() -> Self {
        Self::default()
    }

    /// Register a labelled PC range to count instruction
    /// entries to and accumulate Tcy spent in.
    pub fn add_pc_range(&mut self, start: u16, end: u16, label: &'static str) {
        self.pc_ranges.push(PcRangeProbe {
            start,
            end,
            label,
            hit_count: 0,
            total_cycles: 0,
        });
    }

    /// Register a labelled RAM cell to watch for
    /// transitions.  `initial_value` should be read from the
    /// core's memory at attach time so the first real
    /// transition produces a clean `(tick, new_value)` log
    /// entry instead of a spurious "0 -> initial".
    pub fn add_watched_ram(&mut self, addr: u16, label: &'static str, initial_value: u8) {
        self.watched_ram.push(WatchedRamProbe {
            addr,
            label,
            last_value: initial_value,
            transitions: Vec::new(),
            trigger: None,
        });
    }

    /// Register a labelled RAM cell to watch AND attach a
    /// transition-driven intervention trigger.  When the
    /// watched cell transitions to a value in `[match_min,
    /// match_max]`, the chain writes `target_value` to
    /// `target_addr`.  Used by P3.6b research step 4
    /// (task #65) for the watchdog-causality experiment;
    /// production tests should use `add_watched_ram`.
    pub fn add_watched_ram_with_trigger(
        &mut self,
        addr: u16,
        label: &'static str,
        initial_value: u8,
        match_min: u8,
        match_max: u8,
        target_addr: u16,
        target_value: u8,
    ) {
        self.watched_ram.push(WatchedRamProbe {
            addr,
            label,
            last_value: initial_value,
            transitions: Vec::new(),
            trigger: Some(RamTransitionTrigger {
                match_min,
                match_max,
                target_addr,
                target_value,
                fire_count: 0,
            }),
        });
    }
}

/// Size of the TBLWT staging buffer.  Both supported variants
/// share a 32-byte write block (2455 DS §6.4 / 25K20
/// DS40001303H Tbl 6-1).
pub const TBLWT_HOLDING_SIZE: usize = 32;

/// 2455 flash write block size (DS39632E §6.4).
pub const TBLWT_BLOCK_SIZE_2455: usize = 32;

/// 25K20 flash write block size (DS40001303H Tbl 6-1).
/// 32 bytes for PIC18F25K20 / 45K20.  (PIC18F23K20 / 43K20
/// have a 16-byte block but those are not supported
/// variants.)
pub const TBLWT_BLOCK_SIZE_K20: usize = 32;

/// Options for loading a full Intel HEX image into a fresh
/// [`Core`].  The two optional GOTO bakes model the DLCP MAIN
/// bootloader trampoline in tests that load an app-only V3.x
/// image without the USB boot block.
#[derive(Copy, Clone, Debug, Default, Eq, PartialEq)]
pub struct CoreLoadOptions {
    pub bake_goto_app_entry: Option<u32>,
    pub bake_goto_irq_vector: Option<u32>,
    /// Preserve `Core::new`'s default all-zero CONFIG.  This is
    /// only for tests that intentionally exercise constructor
    /// defaults; firmware builders should leave this `false` so
    /// CONFIG comes from the HEX image as required by §11c FID-04.
    pub preserve_default_config: bool,
}

/// Build a fresh core from all memory windows in a parsed HEX
/// image: flash, data EEPROM, CONFIG, and USER_ID.  This is the
/// canonical loader for firmware-backed tests and PyO3 chain
/// builders.  Datasheet anchors: CONFIG lives at
/// `0x300000..0x30000D` (DS39632E §25 / DS40001303H §23);
/// USER_ID lives at `0x200000..0x200007` (DS39632E §6.7 /
/// DS40001303H §3.1).  Campaign contract: §11c FID-04 in
/// `docs/SIM_REWRITE_RUST_SPEC.md`.
pub fn core_from_hex_image(variant: Variant, image: &HexImage, options: CoreLoadOptions) -> Core {
    let mut core = Core::new(variant);
    let copy_len = core.flash_mut().len().min(image.flash.len());
    core.flash_mut()[..copy_len].copy_from_slice(&image.flash[..copy_len]);

    for (addr, &byte) in image.eeprom.iter().enumerate() {
        core.peripherals.eeprom.set_byte(addr as u8, byte);
    }

    if !options.preserve_default_config {
        core.config = Config::from_bytes(image.config);
        core.peripherals.osc.configure_from_config(&core.config);
    }
    core.user_id = image.user_id;

    if let Some(target) = options.bake_goto_app_entry {
        bake_goto(core.flash_mut(), 0x0000, target);
    }
    if let Some(target) = options.bake_goto_irq_vector {
        bake_goto(core.flash_mut(), 0x0008, target);
    }

    core
}

fn bake_goto(flash: &mut [u8], at: usize, target_byte_addr: u32) {
    assert!(
        target_byte_addr & 1 == 0,
        "GOTO target byte address must be even, got 0x{target_byte_addr:X}"
    );
    assert!(at % 2 == 0, "GOTO bake address must be even, got 0x{at:X}");
    let k_word = target_byte_addr >> 1;
    assert!(
        k_word <= 0x000F_FFFF,
        "PIC18 GOTO target word address out of 20-bit range: 0x{k_word:X}"
    );
    let word1 = 0xEF00u16 | ((k_word as u16) & 0x00FF);
    let word2 = 0xF000u16 | (((k_word >> 8) as u16) & 0x0FFF);
    let end = at + 4;
    assert!(
        end <= flash.len(),
        "GOTO bake range 0x{at:X}..0x{end:X} exceeds flash length 0x{:X}",
        flash.len()
    );
    flash[at] = (word1 & 0x00FF) as u8;
    flash[at + 1] = (word1 >> 8) as u8;
    flash[at + 2] = (word2 & 0x00FF) as u8;
    flash[at + 3] = (word2 >> 8) as u8;
}

impl Core {
    /// Construct an empty core with `flash` and `memory` zero-
    /// filled.  The caller (P1.7's hex loader and P1.6's reset
    /// path) is responsible for populating flash from a hex file
    /// and bringing SFRs to their POR values before instruction
    /// fetch begins.
    pub fn new(variant: Variant) -> Self {
        let flash = vec![0u8; variant.program_memory_bytes()].into_boxed_slice();
        let memory = Memory::new(variant);
        let peripherals = Peripherals::new(variant);
        Core {
            variant,
            flash,
            memory,
            peripherals,
            pc: RESET_VECTOR,
            cycles: 0,
            fast_shadow: FastRegs::default(),
            config: Config::from_bytes([0u8; 14]),
            user_id: [0xFF; 8],
            tblwt_holding: [0xFF; TBLWT_HOLDING_SIZE],
            mclr_held: false,
            run_state: RunState::Running,
            irq_context_stack: [None; 8],
            irq_context_depth: 0,
            wdt_counter_tcy: 0,
            wdt_timeout_pending: false,
            cycle_probe: None,
        }
    }

    /// Block size (in bytes) of the silicon-internal flash
    /// write holding register for this variant.  TBLWT
    /// indexes into `tblwt_holding` by `TBLPTR & (block_size
    /// - 1)`; EECON1.WR commits the buffer's
    /// `block_size` bytes back to flash / user-id / config.
    /// Task #17.
    pub const fn tblwt_block_size(&self) -> usize {
        match self.variant {
            Variant::Pic18F2455 => TBLWT_BLOCK_SIZE_2455,
            Variant::Pic18F25K20 => TBLWT_BLOCK_SIZE_K20,
        }
    }

    /// Snapshot W/STATUS/BSR into the fast shadow stack.
    /// Called from `CALL FAST` (s=1) and from the IRQ
    /// dispatcher when IPEN=1.  Per DS39632E §5.5.3 the
    /// shadow is 1-deep -- nesting overwrites the prior
    /// snapshot (firmware that nests CALL FAST inside an
    /// IRQ does so at its own peril; V3.1 doesn't).
    pub fn save_fast_regs(&mut self) {
        self.fast_shadow = FastRegs {
            wreg: self
                .memory
                .read_raw(crate::memory::Address::from_raw(0xFE8)),
            status: self
                .memory
                .read_raw(crate::memory::Address::from_raw(0xFD8)),
            bsr: self
                .memory
                .read_raw(crate::memory::Address::from_raw(0xFE0)),
        };
    }

    /// Restore W/STATUS/BSR from the fast shadow stack.
    /// Called from `RETURN FAST` and `RETFIE FAST`.  The
    /// shadow stays populated across the restore (1-deep
    /// silicon FIFO -- the same value would be re-restored
    /// on a follow-up RETURN FAST without an intervening
    /// CALL FAST, but firmware doesn't typically do that).
    ///
    /// STATUS unimplemented bits (7..5) read as 0 per DS
    /// Register 5-2; BSR <7:4> unimplemented per §5.3.2.
    /// `save_fast_regs` snapshots via `read_raw` which is
    /// the direct backing byte, NOT the masked-on-write
    /// path, so a peripheral or reset path that wrote raw
    /// bytes could leave dirty bits in the snapshot.  Mask
    /// defensively on restore so the SFR window stays
    /// silicon-clean regardless of how the snapshot was
    /// produced.
    pub fn restore_fast_regs(&mut self) {
        let snap = self.fast_shadow;
        self.memory
            .write_raw(crate::memory::Address::from_raw(0xFE8), snap.wreg);
        self.memory
            .write_raw(crate::memory::Address::from_raw(0xFD8), snap.status & 0x1F);
        self.memory
            .write_raw(crate::memory::Address::from_raw(0xFE0), snap.bsr & 0x0F);
    }

    pub fn push_irq_context(&mut self, context: IrqContext) {
        if self.irq_context_depth < self.irq_context_stack.len() {
            self.irq_context_stack[self.irq_context_depth] = Some(context);
            self.irq_context_depth += 1;
        }
    }

    pub fn pop_irq_context(&mut self) -> Option<IrqContext> {
        if self.irq_context_depth == 0 {
            return None;
        }
        self.irq_context_depth -= 1;
        self.irq_context_stack[self.irq_context_depth].take()
    }

    pub fn clear_irq_context(&mut self) {
        self.irq_context_stack = [None; 8];
        self.irq_context_depth = 0;
    }

    /// Variant this core was constructed for.
    pub const fn variant(&self) -> Variant {
        self.variant
    }

    /// Borrow the program-memory bytes (read-only).  The hex
    /// loader (P1.7) writes through [`Self::flash_mut`].
    pub fn flash(&self) -> &[u8] {
        &self.flash
    }

    /// Mutable borrow of the program-memory bytes.  Used by the
    /// hex loader and by the table-write instructions
    /// (`TBLWT*`) which can self-program flash on PIC18.
    pub fn flash_mut(&mut self) -> &mut [u8] {
        &mut self.flash
    }

    /// Read the program counter.
    pub const fn pc(&self) -> u32 {
        self.pc
    }

    /// Set the program counter.  Reset and the GOTO/CALL/RETURN
    /// family of instructions go through here; raw assignment
    /// during state restore (P5.1 snapshot/restore) too.
    ///
    /// The PIC18 PC is 21 bits AND byte-addressed but always
    /// instruction-aligned: PCL bit 0 is hard-wired to 0 in
    /// silicon (DS39632E §5.5.1, DS41303G §5.5.1) so instruction
    /// fetch never sees an odd PC.  Mask both the upper bits
    /// (above bit 20) and bit 0 to enforce that invariant here;
    /// a caller that hands us an odd value (`pc | 1`) loses
    /// only the always-zero LSB.
    pub fn set_pc(&mut self, pc: u32) {
        self.pc = pc & 0x001F_FFFE;
    }

    /// Total instruction cycles elapsed since the last reset.
    pub const fn cycles(&self) -> u64 {
        self.cycles
    }

    pub const fn ticks_per_tcy(&self) -> u32 {
        self.peripherals.osc.ticks_per_tcy()
    }

    /// Reset the cycle counter to 0.  Phase-3.5's
    /// `Chain::schedule_initial_steps` uses this to make
    /// re-bootstrap (e.g. mid-run MCLR) safe -- the
    /// schedule arithmetic in
    /// `Chain::schedule_next_core_step` is relative to
    /// the boot epoch, so the cycle counter needs to be
    /// 0 at re-bootstrap or the arithmetic carries
    /// pre-reset history forward.  Existing single-core
    /// tests that call `apply_reset` directly are not
    /// affected because they construct a fresh `Core`
    /// (cycles=0) before applying reset.
    ///
    /// Marked `_for_test` to discourage misuse in
    /// non-bootstrap paths -- on real silicon the
    /// "instruction cycle counter" concept is purely a
    /// simulator artefact, so resetting it is always a
    /// model-level operation.
    pub fn reset_cycles_for_test(&mut self) {
        self.cycles = 0;
    }

    pub const fn wdt_counter_tcy(&self) -> u64 {
        self.wdt_counter_tcy
    }

    pub const fn wdt_timeout_tcy(&self) -> u64 {
        WDT_BASE_TCY << self.config.wdtps()
    }

    pub fn clear_wdt(&mut self) {
        self.wdt_counter_tcy = 0;
        self.wdt_timeout_pending = false;
    }

    pub fn reset_power_state(&mut self) {
        self.run_state = RunState::Running;
        self.clear_irq_context();
        self.clear_wdt();
    }

    pub fn take_wdt_timeout_pending(&mut self) -> bool {
        let pending = self.wdt_timeout_pending;
        self.wdt_timeout_pending = false;
        pending
    }

    pub fn advance_halted_cycles(&mut self, n: u32) {
        if self.run_state == RunState::Idle {
            self.peripherals.tick_tcy(n, &mut self.memory);
        } else if self.run_state == RunState::Sleep {
            self.peripherals.tick_sleep_tcy(n, &mut self.memory);
            if irq::is_irq_pending(&self.memory) {
                self.run_state = RunState::Running;
            }
        }
        self.tick_wdt(n);
    }

    /// Advance the cycle counter by `n` Tcy.  Called by the
    /// instruction interpreter (P1.2) once per instruction.
    /// Also ticks every peripheral by the same Tcy budget so
    /// time-driven state machines (baud generator, timers,
    /// ADC sample/conv, EEPROM post-write completion) stay
    /// in lock-step with the executor.
    pub fn advance_cycles(&mut self, n: u32) {
        self.cycles = self.cycles.saturating_add(n as u64);
        self.peripherals.tick_tcy(n, &mut self.memory);
        self.tick_wdt(n);
    }

    fn wdt_enabled(&self) -> bool {
        self.config.wdten() || (self.memory.read_raw(Address::from_raw(WDTCON_ADDR)) & 0x01) != 0
    }

    fn tick_wdt(&mut self, n: u32) {
        if !self.wdt_enabled() {
            self.wdt_counter_tcy = 0;
            return;
        }
        self.wdt_counter_tcy = self.wdt_counter_tcy.saturating_add(n as u64);
        if self.wdt_counter_tcy < self.wdt_timeout_tcy() {
            return;
        }
        self.wdt_counter_tcy = 0;
        if self.run_state == RunState::Running {
            self.wdt_timeout_pending = true;
        } else {
            self.run_state = RunState::Running;
            let rcon = self.memory.read_raw(Address::from_raw(RCON_ADDR));
            self.memory
                .write_raw(Address::from_raw(RCON_ADDR), rcon & !RCON_TO);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn new_core_is_zero_filled() {
        let core = Core::new(Variant::Pic18F25K20);
        assert_eq!(core.pc(), RESET_VECTOR);
        assert_eq!(core.cycles(), 0);
        assert!(core.flash().iter().all(|&b| b == 0));
        assert!(core.memory.as_slice().iter().all(|&b| b == 0));
    }

    #[test]
    fn flash_size_matches_variant() {
        // Both variants currently allocate full 32 KiB; see
        // `Variant::program_memory_bytes` for rationale.
        assert_eq!(Core::new(Variant::Pic18F25K20).flash().len(), 32 * 1024);
        assert_eq!(Core::new(Variant::Pic18F2455).flash().len(), 32 * 1024);
    }

    #[test]
    fn data_memory_size_matches_variant() {
        assert_eq!(
            Core::new(Variant::Pic18F25K20).memory.as_slice().len(),
            4096
        );
        assert_eq!(Core::new(Variant::Pic18F2455).memory.as_slice().len(), 4096);
    }

    #[test]
    fn pc_is_masked_to_21_bits_and_word_aligned() {
        let mut core = Core::new(Variant::Pic18F2455);
        // 0xFFFF_FFFF asks for "all bits set"; we expect both the
        // upper-11-bits clear AND bit 0 clear (PCL[0] is hard-
        // wired to 0 on PIC18).  Result: 0x001F_FFFE, the largest
        // architecturally legal PC value.
        core.set_pc(0xFFFF_FFFF);
        assert_eq!(core.pc(), 0x001F_FFFE);
    }

    #[test]
    fn pc_set_drops_odd_lsb() {
        // A caller handing us PC|1 (e.g., from a buggy table
        // read or a state restore that lost alignment) should
        // see the LSB silently cleared, not a stored odd value.
        let mut core = Core::new(Variant::Pic18F2455);
        core.set_pc(0x4577);
        assert_eq!(core.pc(), 0x4576);
    }

    #[test]
    fn advance_cycles_accumulates() {
        let mut core = Core::new(Variant::Pic18F25K20);
        core.advance_cycles(1);
        core.advance_cycles(2);
        assert_eq!(core.cycles(), 3);
    }

    #[test]
    fn advance_cycles_saturates_at_u64_max() {
        let mut core = Core::new(Variant::Pic18F25K20);
        core.cycles = u64::MAX - 1;
        core.advance_cycles(10);
        assert_eq!(core.cycles(), u64::MAX);
    }
}
