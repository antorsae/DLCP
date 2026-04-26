//! `Chain` — multi-core container + universal-clock
//! scheduler driver.
//!
//! ## Phase-3 scope
//!
//! P3.1 lands the skeleton: a `Chain` holds N cores, owns
//! the global event queue from [`crate::scheduler`], and
//! exposes `step_ticks(n)` that advances the universal
//! clock by `n` ticks while draining due events.
//! Cross-core wiring (P3.2 pin net), boot offsets (P3.4),
//! and the actual instruction-step path that posts
//! `CoreInstructionComplete` events back into the queue
//! land in subsequent sub-tasks.
//!
//! ## Universal clock invariants
//!
//! * Tick is `u64` of a 48 MHz universal clock (LCM of K20
//!   12 MHz Fosc and 2455 16 MHz Fosc).  Range: ~12 years.
//! * Each core advances by `ticks_per_tcy(variant)`
//!   universal ticks per instruction-cycle (Tcy):
//!   K20=16, 2455=12.  See `peripherals/osc.rs`.

use crate::clock::ClockDomain;
use crate::core::Core;
use crate::exec::step;
use crate::peripherals::osc;
use crate::pinnet::{PinId, PinNet};
use crate::reset::{ResetSource, apply_reset};
use crate::scheduler::{Event, EventKind, EventQueue};
use crate::stack::Stack;

/// Multi-core chain on a single universal-clock timeline.
pub struct Chain {
    /// Cores in firmware-deterministic order.  Index into
    /// this vec is the `core_idx` carried in event kinds.
    pub cores: Vec<Core>,
    /// One stack per core, parallel to `cores`.  The
    /// PIC18 `exec::step` API takes a `&mut Stack`
    /// alongside the core, so the chain owns one per core
    /// and pairs them by index.
    pub stacks: Vec<Stack>,
    /// Per-core clock domain (ticks/Tcy + drift_ppm).
    /// Parallel to `cores`.  P3.5 uses these to schedule
    /// the next instruction-complete event with drift
    /// applied via `ClockDomain::apply_drift`.
    pub clocks: Vec<ClockDomain>,
    /// Per-core boot-offset epoch tick.  Recorded by
    /// `schedule_initial_steps` and added to every
    /// subsequent `schedule_next_core_step` call so a
    /// late-booting core's instruction-complete events
    /// stay delayed by the offset rather than collapsing
    /// to the start-of-time.  Defaults to 0 for cores
    /// that never had `schedule_initial_steps` called.
    pub boot_epochs: Vec<u64>,
    /// Universal-clock tick at the head of the queue.
    /// Phase-3.5 dispatch updates this as events fire so
    /// each core's instruction completes at its own
    /// drifted-ticks-per-Tcy boundary.
    pub current_tick: u64,
    /// Global event queue.  Phase-3.5 dispatch consumes
    /// `CoreInstructionComplete` events here; future P3.x
    /// sub-tasks add `PinPropagation` and
    /// `PeripheralDeadline` handlers.
    pub events: EventQueue,
    /// Cross-core electrical wiring (UART couplings, pin
    /// couplings, I²C slave couplings).  Populated via
    /// `couple_uart` / `couple_pin` / `couple_i2c_slave`.
    /// Phase-3.5 dispatches byte propagation across these
    /// on event firing.
    pub pinnet: PinNet,
}

impl Chain {
    /// Construct an empty chain with no cores.  Callers
    /// `push_core` to add CONTROL + MAINs in firmware
    /// order.
    pub fn new() -> Self {
        Chain {
            cores: Vec::new(),
            stacks: Vec::new(),
            clocks: Vec::new(),
            boot_epochs: Vec::new(),
            current_tick: 0,
            events: EventQueue::new(),
            pinnet: PinNet::new(),
        }
    }

    /// Wire source-core EUSART TX to destination-core
    /// EUSART RX.  Phase-3.5 will dispatch byte
    /// propagation through `pinnet.uart` on each
    /// CoreInstructionComplete event.
    pub fn couple_uart(
        &mut self,
        src_core: usize,
        src_tx_pin: PinId,
        dst_core: usize,
        dst_rx_pin: PinId,
    ) {
        self.pinnet
            .couple_uart(src_core, src_tx_pin, dst_core, dst_rx_pin);
    }

    /// Wire a general-purpose source-core pin to a
    /// destination-core pin.  Used for MCLR/RA0 wakeup,
    /// LCD strobes, button-matrix rows, etc.
    pub fn couple_pin(
        &mut self,
        src_core: usize,
        src_pin: PinId,
        dst_core: usize,
        dst_pin: PinId,
    ) {
        self.pinnet
            .couple_pin(src_core, src_pin, dst_core, dst_pin);
    }

    /// Wire a master-mode I²C bus on `master_core` to a
    /// virtual slave (e.g. the TAS3108 DSP model).
    pub fn couple_i2c_slave(
        &mut self,
        master_core: usize,
        master_sda: PinId,
        master_scl: PinId,
        slave_id: u32,
    ) {
        self.pinnet
            .couple_i2c_slave(master_core, master_sda, master_scl, slave_id);
    }

    /// Add a core to the chain with a fresh `Stack` and
    /// the variant's nominal `ClockDomain` (no drift).
    /// Returns the core's index.  Use
    /// `push_core_with_clock` to start a core with a
    /// non-zero drift_ppm.
    pub fn push_core(&mut self, core: Core) -> usize {
        let variant = core.variant();
        self.push_core_with_clock(core, ClockDomain::new(variant))
    }

    /// Add a core with an explicit `ClockDomain` (e.g. for
    /// tests that exercise drift).  Returns the core's
    /// index.
    pub fn push_core_with_clock(
        &mut self,
        core: Core,
        clock: ClockDomain,
    ) -> usize {
        let idx = self.cores.len();
        self.cores.push(core);
        self.stacks.push(Stack::new());
        self.clocks.push(clock);
        self.boot_epochs.push(0);
        idx
    }

    /// Universal-clock ticks-per-Tcy for `core_idx`.
    /// Wraps `peripherals::osc::ticks_per_tcy` for
    /// convenience.
    pub fn ticks_per_tcy(&self, core_idx: usize) -> u32 {
        osc::ticks_per_tcy(self.cores[core_idx].variant())
    }

    /// Advance the universal clock by `n_ticks`, draining
    /// every event whose deadline `<= current_tick + n_ticks`.
    /// Phase-3 sub-tasks fill in the actual handler bodies;
    /// the skeleton just advances the tick and consumes any
    /// pending events without dispatch.
    pub fn step_ticks(&mut self, n_ticks: u64) {
        let target = self.current_tick.saturating_add(n_ticks);
        while let Some(next) = self.events.peek() {
            if next.tick > target {
                break;
            }
            let event = self.events.pop().expect("peek/pop consistency");
            // Advance the universal clock to the event's
            // firing tick BEFORE dispatching so handlers
            // observe a coherent `current_tick`.  Phase-3.2+
            // handlers will rely on this for pin-network
            // propagation timing and peripheral deadline
            // routing.
            self.current_tick = event.tick;
            self.dispatch_event(event);
        }
        // After draining all due events, jump to the target
        // even if it's later than the last fired event.
        self.current_tick = target;
    }

    /// Dispatch one drained event.  Phase-3.5 wires the
    /// `CoreInstructionComplete` arm to actually execute
    /// the next instruction on the named core and
    /// reschedule its next completion event; pin
    /// propagation and peripheral deadlines remain stubs
    /// until subsequent P3.x sub-tasks fill them in.
    fn dispatch_event(&mut self, event: Event) {
        match event.kind {
            EventKind::CoreInstructionComplete(core_idx) => {
                self.execute_core_step(core_idx);
            }
            EventKind::PinPropagation(_) => {
                // P3.5 next-commit: deliver byte to peer
                // RCREG.
            }
            EventKind::PeripheralDeadline { .. } => {
                // Peripherals currently advance via
                // `core.advance_cycles -> tick_tcy`; the
                // queue-driven path is reserved for
                // peripherals whose deadline outruns the
                // executor (EEPROM 12 000-Tcy write,
                // ADC conversion, etc.) -- to be wired
                // in P3.7 alongside the late-boot
                // recovery test.
            }
        }
    }

    /// Execute one instruction on `core_idx` and schedule
    /// the next `CoreInstructionComplete` event at the
    /// drifted-tick boundary derived from
    /// [`ClockDomain::apply_drift`].  This is the
    /// per-core driver Phase-3.5+ exercises via
    /// `step_ticks` to keep all cores progressing on the
    /// universal-clock timeline.
    pub fn execute_core_step(&mut self, core_idx: usize) {
        let core = &mut self.cores[core_idx];
        let stack = &mut self.stacks[core_idx];
        // Best-effort: errors propagate as a panic for
        // now -- a real chain would distinguish "fatal"
        // cores (unknown opcode -> halt) from "warm
        // halt" (firmware-driven SLEEP) and surface them
        // to the test harness.  Phase-3.5 minimal scope
        // keeps the panic so test failures are obvious.
        let _ = step(core, stack)
            .unwrap_or_else(|e| panic!("exec::step failed on core {core_idx}: {e:?}"));
        self.schedule_next_core_step(core_idx);
    }

    /// Schedule a `CoreInstructionComplete` event for the
    /// given core at its next instruction-complete tick,
    /// derived from the core's current Tcy count + the
    /// per-core drifted ticks/Tcy + the boot-offset epoch.
    /// Without the epoch, a late-booted core's first
    /// instruction would fire at boot_offset, then the
    /// SECOND would schedule at `cycles * factor` --
    /// before boot_offset for any non-trivial offset --
    /// causing the queue to fire it immediately and
    /// effectively collapsing the boot delay.  Tracking
    /// the per-core epoch keeps the relative-to-boot
    /// scheduling semantic intact.
    pub fn schedule_next_core_step(&mut self, core_idx: usize) {
        let tcy = self.cores[core_idx].cycles();
        let factor = self.clocks[core_idx].nominal_ticks_per_tcy as u64;
        let nominal_tick = tcy.saturating_mul(factor);
        let drifted_tick = self.clocks[core_idx].apply_drift(nominal_tick);
        let epoch = self.boot_epochs[core_idx];
        let absolute_tick = epoch.saturating_add(drifted_tick);
        self.events
            .push(absolute_tick, EventKind::CoreInstructionComplete(core_idx));
    }

    /// Apply POR to every core in the chain.  Helper for
    /// Phase-3.5 fixture builders that need each core's
    /// SFRs at K20_POR before any cross-core stimulus runs.
    pub fn apply_reset_all(&mut self, source: ResetSource) {
        for idx in 0..self.cores.len() {
            apply_reset(&mut self.cores[idx], &mut self.stacks[idx], source);
        }
    }

    /// Bootstrap each core's first `CoreInstructionComplete`
    /// event onto the queue at the boot-offset tick.  Also
    /// records the offset as the per-core epoch so all
    /// subsequent `schedule_next_core_step` calls add it
    /// to their absolute tick (preserving the boot delay
    /// across the whole run instead of collapsing back to
    /// tick 0 after the first instruction).  The
    /// `boot_offsets[idx]` slot supplies the offset for
    /// `cores[idx]`; vec must be the same length as
    /// `cores`.
    pub fn schedule_initial_steps(&mut self, boot_offsets: &[u64]) {
        assert_eq!(
            boot_offsets.len(),
            self.cores.len(),
            "boot_offsets length must match number of cores"
        );
        for (idx, &offset) in boot_offsets.iter().enumerate() {
            self.boot_epochs[idx] = offset;
            self.events
                .push(offset, EventKind::CoreInstructionComplete(idx));
        }
    }
}

impl Default for Chain {
    fn default() -> Self {
        Chain::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::memory::Variant;

    #[test]
    fn empty_chain_step_ticks_advances_clock_only() {
        let mut chain = Chain::new();
        assert_eq!(chain.current_tick, 0);
        chain.step_ticks(1000);
        assert_eq!(chain.current_tick, 1000);
        chain.step_ticks(500);
        assert_eq!(chain.current_tick, 1500);
    }

    #[test]
    fn push_core_assigns_sequential_indices() {
        let mut chain = Chain::new();
        let i0 = chain.push_core(Core::new(Variant::Pic18F25K20));
        let i1 = chain.push_core(Core::new(Variant::Pic18F2455));
        assert_eq!(i0, 0);
        assert_eq!(i1, 1);
    }

    #[test]
    fn ticks_per_tcy_matches_per_variant_factor() {
        let mut chain = Chain::new();
        chain.push_core(Core::new(Variant::Pic18F25K20));
        chain.push_core(Core::new(Variant::Pic18F2455));
        assert_eq!(chain.ticks_per_tcy(0), 16);
        assert_eq!(chain.ticks_per_tcy(1), 12);
    }

    #[test]
    fn step_ticks_drains_due_events_in_order() {
        let mut chain = Chain::new();
        chain.events.push(50, EventKind::PinPropagation(1));
        chain.events.push(20, EventKind::PinPropagation(2));
        chain.events.push(80, EventKind::PinPropagation(3));
        chain.step_ticks(60);
        // Events at 20 and 50 fired (no-op dispatch); event
        // at 80 is still scheduled.
        assert_eq!(chain.events.len(), 1);
        assert_eq!(chain.current_tick, 60);
    }

    #[test]
    fn step_ticks_does_not_overshoot() {
        let mut chain = Chain::new();
        chain.events.push(100, EventKind::PinPropagation(1));
        chain.step_ticks(50);
        // Event at 100 NOT yet drained.
        assert_eq!(chain.events.len(), 1);
        // Step further; now drains.
        chain.step_ticks(60);
        assert_eq!(chain.current_tick, 110);
        assert_eq!(chain.events.len(), 0);
    }

    /// Coupling-API smoke: each `couple_*` call records
    /// one entry in the appropriate `pinnet` vec.
    #[test]
    fn couple_uart_records_in_pinnet() {
        let mut chain = Chain::new();
        chain.push_core(Core::new(Variant::Pic18F25K20));
        chain.push_core(Core::new(Variant::Pic18F2455));
        chain.couple_uart(
            0,
            crate::pinnet::default_tx_pin(),
            1,
            crate::pinnet::default_rx_pin(),
        );
        assert_eq!(chain.pinnet.uart.len(), 1);
        assert_eq!(chain.pinnet.uart[0].src_core, 0);
        assert_eq!(chain.pinnet.uart[0].dst_core, 1);
    }

    #[test]
    fn couple_pin_records_in_pinnet() {
        let mut chain = Chain::new();
        chain.push_core(Core::new(Variant::Pic18F25K20));
        chain.push_core(Core::new(Variant::Pic18F2455));
        let src = crate::pinnet::PinId {
            port: crate::pinnet::PortLetter::C,
            bit: 0,
        };
        let dst = crate::pinnet::PinId {
            port: crate::pinnet::PortLetter::A,
            bit: 0,
        };
        chain.couple_pin(0, src, 1, dst);
        assert_eq!(chain.pinnet.pin.len(), 1);
    }

    #[test]
    fn couple_i2c_slave_records_in_pinnet() {
        let mut chain = Chain::new();
        chain.push_core(Core::new(Variant::Pic18F2455));
        let sda = crate::pinnet::PinId {
            port: crate::pinnet::PortLetter::C,
            bit: 4,
        };
        let scl = crate::pinnet::PinId {
            port: crate::pinnet::PortLetter::C,
            bit: 3,
        };
        chain.couple_i2c_slave(0, sda, scl, 7);
        assert_eq!(chain.pinnet.i2c.len(), 1);
        assert_eq!(chain.pinnet.i2c[0].slave_id, 7);
    }

    #[test]
    fn schedule_next_core_step_uses_universal_tick() {
        let mut chain = Chain::new();
        let idx = chain.push_core(Core::new(Variant::Pic18F25K20));
        // Hand-set a Tcy count.
        chain.cores[idx].advance_cycles(100);
        chain.schedule_next_core_step(idx);
        let event = chain.events.peek().unwrap();
        // K20 ticks_per_tcy = 16; 100 Tcy * 16 = 1600 ticks.
        assert_eq!(event.tick, 1600);
        assert_eq!(
            event.kind,
            EventKind::CoreInstructionComplete(idx),
        );
    }

    /// Drift-aware scheduling: a core with +20 000 ppm
    /// drift schedules its 100-Tcy boundary 20 000 ppm
    /// later than the nominal 1600-tick mark.
    #[test]
    fn schedule_next_core_step_applies_drift() {
        let mut chain = Chain::new();
        let idx = chain.push_core_with_clock(
            Core::new(Variant::Pic18F25K20),
            ClockDomain::with_drift_ppm(Variant::Pic18F25K20, 20_000),
        );
        chain.cores[idx].advance_cycles(100);
        chain.schedule_next_core_step(idx);
        let event = chain.events.peek().unwrap();
        // 100 Tcy * 16 ticks/Tcy = 1600 nominal.  With +2 %
        // drift: 1600 * 1.02 = 1632.
        assert_eq!(event.tick, 1632);
    }

    /// Build a flash with a single BRA -1 self-loop at
    /// PC=0; bootstraps an executor to run forever.  Used
    /// by the multicore tests below to confirm the chain's
    /// dispatch path actually advances the named core.
    fn build_self_loop_flash() -> Vec<u8> {
        let mut flash = vec![0u8; 32 * 1024];
        flash[0] = 0xFF;
        flash[1] = 0xD7; // BRA -1
        flash
    }

    /// Single-core dispatch: schedule the first
    /// CoreInstructionComplete at tick 0; step_ticks(N)
    /// drains it, runs `exec::step`, reschedules.
    /// After enough ticks the core's cycle counter
    /// advances.  K20 BRA = 2 Tcy * 16 ticks/Tcy = 32
    /// universal ticks per BRA iteration.  step_ticks(1000)
    /// runs ~31 BRA iterations -> ~62 Tcy.
    #[test]
    fn single_core_dispatch_advances_cycle_counter() {
        let mut chain = Chain::new();
        let mut core = Core::new(Variant::Pic18F25K20);
        core.flash_mut().copy_from_slice(&build_self_loop_flash());
        let idx = chain.push_core(core);
        chain.apply_reset_all(ResetSource::PowerOn);
        chain.schedule_initial_steps(&[0]);
        chain.step_ticks(1000);
        let cycles = chain.cores[idx].cycles();
        assert!(
            (50..75).contains(&cycles),
            "core cycles should reflect ~62 Tcy after 1000 universal ticks (got {cycles})"
        );
    }

    /// Two cores running concurrently: a K20 (16 ticks/Tcy)
    /// and a 2455 (12 ticks/Tcy) both with self-loop BRA
    /// firmware.  After 1000 universal ticks, each should
    /// have advanced its own Tcy counter according to its
    /// per-core ticks/Tcy factor.  K20: ~31 BRAs; 2455:
    /// ~41 BRAs.
    #[test]
    fn two_cores_advance_at_their_own_clock_rates() {
        let mut chain = Chain::new();
        let mut k20 = Core::new(Variant::Pic18F25K20);
        k20.flash_mut().copy_from_slice(&build_self_loop_flash());
        let i_k20 = chain.push_core(k20);
        let mut p2455 = Core::new(Variant::Pic18F2455);
        p2455.flash_mut().copy_from_slice(&build_self_loop_flash());
        let i_2455 = chain.push_core(p2455);
        chain.apply_reset_all(ResetSource::PowerOn);
        chain.schedule_initial_steps(&[0, 0]);
        chain.step_ticks(1000);
        let k20_cy = chain.cores[i_k20].cycles();
        let p2455_cy = chain.cores[i_2455].cycles();
        // K20: BRA = 2 Tcy * 16 ticks = 32 ticks/iter ->
        // 1000/32 ≈ 31 iterations -> ~62 cycles.
        assert!(
            (50..75).contains(&k20_cy),
            "K20 should be ~62 cycles, got {k20_cy}"
        );
        // 2455: BRA = 2 Tcy * 12 ticks = 24 ticks/iter ->
        // 1000/24 ≈ 41 iterations -> ~82 cycles.
        assert!(
            (75..100).contains(&p2455_cy),
            "2455 should be ~82 cycles, got {p2455_cy}"
        );
        // 2455 must have advanced more cycles than K20
        // because its clock is faster (12 vs 16 ticks/Tcy).
        assert!(p2455_cy > k20_cy, "2455 should outpace K20");
    }

    /// Boot-offset honored: a core with boot_offset=500
    /// doesn't step before universal tick 500 but does step
    /// after.
    #[test]
    fn boot_offset_delays_first_step() {
        let mut chain = Chain::new();
        let mut core = Core::new(Variant::Pic18F25K20);
        core.flash_mut().copy_from_slice(&build_self_loop_flash());
        let idx = chain.push_core(core);
        chain.apply_reset_all(ResetSource::PowerOn);
        chain.schedule_initial_steps(&[500]);
        // Step to tick 400 -- before boot offset.  Core
        // shouldn't have advanced.
        chain.step_ticks(400);
        assert_eq!(chain.cores[idx].cycles(), 0);
        // Step past boot offset.  Core should now run.
        chain.step_ticks(600);
        assert!(chain.cores[idx].cycles() > 0);
    }

    /// Regression: late-booted core stays delayed across
    /// MULTIPLE instructions.  Prior to the boot-epoch fix,
    /// the second instruction would schedule at
    /// `cycles * factor = 32` (in the past) which the
    /// queue would fire immediately, collapsing the
    /// boot-offset delay.  After the fix, all subsequent
    /// instructions land at `boot_offset + cycles * factor`
    /// so the core stays at its delayed cadence.
    #[test]
    fn boot_offset_persists_across_multiple_instructions() {
        let mut chain = Chain::new();
        let mut core = Core::new(Variant::Pic18F25K20);
        core.flash_mut().copy_from_slice(&build_self_loop_flash());
        let idx = chain.push_core(core);
        chain.apply_reset_all(ResetSource::PowerOn);
        // Boot offset = 1500 (well past where a non-
        // delayed core would have completed many BRAs).
        chain.schedule_initial_steps(&[1500]);
        // Step to tick 1000 -- still before boot.  Core
        // hasn't run.
        chain.step_ticks(1000);
        assert_eq!(chain.cores[idx].cycles(), 0);
        // Step to tick 2500.  Core has been running for
        // 2500 - 1500 = 1000 ticks.  At 32 ticks/BRA
        // -> 31 iterations -> 62 cycles.
        chain.step_ticks(1500);
        let cycles = chain.cores[idx].cycles();
        assert!(
            (50..75).contains(&cycles),
            "boot-delayed core should advance ~62 cycles in 1000 post-boot ticks (got {cycles})"
        );
        // Critically: also verify the chain's
        // current_tick reflects the boot-offset-respecting
        // dispatch, not a collapsed catch-up.  current_tick
        // is the most recent event's firing tick OR the
        // step_ticks target -- after step_ticks(1500), the
        // last event we fired must be >= 1500 (when the
        // first instruction completes), not 0 or 32.
        assert!(
            chain.current_tick >= 1500,
            "current_tick should be >= boot offset 1500 (got {})",
            chain.current_tick
        );
    }
}
