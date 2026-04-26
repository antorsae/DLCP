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

    /// Dispatch one drained event.  Phase-3.5 wires:
    ///   * `CoreInstructionComplete`: execute one
    ///     instruction on the named core, drain any
    ///     completed TX bytes into UartByteDelivery
    ///     events, reschedule the next completion event.
    ///   * `UartByteDelivery`: deliver the byte to the
    ///     destination core's EUSART RX via
    ///     `Eusart::deliver_rx_byte`.
    /// `PinPropagation` (general-purpose pin events) and
    /// `PeripheralDeadline` remain stubs until subsequent
    /// P3.x sub-tasks fill them in.
    fn dispatch_event(&mut self, event: Event) {
        match event.kind {
            EventKind::CoreInstructionComplete(core_idx) => {
                self.execute_core_step(core_idx);
            }
            EventKind::UartByteDelivery {
                uart_coupling_idx,
                byte,
            } => {
                self.deliver_uart_byte(uart_coupling_idx, byte);
            }
            EventKind::PinPropagation(_) => {
                // General-purpose pin events deferred to
                // P3.7 alongside the late-boot recovery
                // test that exercises MCLR / RA0 wakeup.
            }
            EventKind::PeripheralDeadline { .. } => {
                // Peripherals currently advance via
                // `core.advance_cycles -> tick_tcy`; the
                // queue-driven path is reserved for
                // peripherals whose deadline outruns the
                // executor (EEPROM 12 000-Tcy write, etc.)
                // -- to be wired alongside multi-core
                // EEPROM-write-time parity in P3.7.
            }
        }
    }

    /// Deliver a UART byte from a source-core's EUSART
    /// TX to the wired destination-core's EUSART RX.  The
    /// `uart_coupling_idx` indexes `pinnet.uart`; the byte
    /// is loaded into RCREG + sets RCIF on the destination
    /// (gated on the destination's RCSTA.SPEN AND CREN).
    fn deliver_uart_byte(&mut self, uart_coupling_idx: usize, byte: u8) {
        let coupling = match self.pinnet.uart.get(uart_coupling_idx) {
            Some(c) => c.clone(),
            None => return,
        };
        // Borrow-checker: take a single &mut Core for the
        // destination, then split-borrow `peripherals` and
        // `memory` -- they're disjoint pub fields so the
        // compiler accepts the simultaneous &mut on each.
        let dst_core = &mut self.cores[coupling.dst_core];
        let memory = &mut dst_core.memory;
        let eusart = &mut dst_core.peripherals.eusart;
        eusart.deliver_rx_byte(byte, memory);
    }

    /// Execute one instruction on `core_idx`, drain any
    /// EUSART TX bytes that completed shifting during the
    /// step into `UartByteDelivery` events for the wired
    /// peer cores, and schedule the next
    /// `CoreInstructionComplete` event at the drifted-tick
    /// boundary derived from
    /// [`ClockDomain::apply_drift`].
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
        self.drain_completed_tx_bytes(core_idx);
        self.schedule_next_core_step(core_idx);
    }

    /// Pull any bytes that the source-core EUSART
    /// completed shifting since the last drain, and post a
    /// `UartByteDelivery` event for each matching UART
    /// coupling at the current universal tick (instant
    /// delivery; pin-network propagation delay is a
    /// Phase-4 dual-run refinement).
    fn drain_completed_tx_bytes(&mut self, src_core_idx: usize) {
        // Snapshot which UART couplings source from this
        // core (by index).  We need the snapshot up-front
        // because we'll mutably borrow the source core's
        // EUSART next.
        let matching_couplings: Vec<usize> = self
            .pinnet
            .uart
            .iter()
            .enumerate()
            .filter_map(|(idx, c)| {
                if c.src_core == src_core_idx {
                    Some(idx)
                } else {
                    None
                }
            })
            .collect();
        if matching_couplings.is_empty() {
            // Nothing wired -- still drain the FIFO so it
            // doesn't accumulate and force-deliver
            // already-aged bytes when a coupling lands
            // later.
            let core = &mut self.cores[src_core_idx];
            while core.peripherals.eusart.take_completed_tx_byte().is_some() {}
            return;
        }
        // Drain bytes from the source core's EUSART into
        // a local Vec first (split-borrow: the &mut on
        // self.cores conflicts with a later self.events
        // push if held simultaneously).
        let bytes: Vec<u8> = {
            let src_core = &mut self.cores[src_core_idx];
            let eusart = &mut src_core.peripherals.eusart;
            let mut acc = Vec::new();
            while let Some(byte) = eusart.take_completed_tx_byte() {
                acc.push(byte);
            }
            acc
        };
        // Now post a UartByteDelivery event per (byte,
        // coupling) pair at the current tick.
        let now = self.current_tick;
        for byte in bytes {
            for &coupling_idx in &matching_couplings {
                self.events.push(
                    now,
                    EventKind::UartByteDelivery {
                        uart_coupling_idx: coupling_idx,
                        byte,
                    },
                );
            }
        }
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
    ///
    /// Re-bootstrap safety: any pending events in the
    /// queue are dropped first and per-core cycle counters
    /// are reset to 0.  This makes the call safe to use
    /// post-MCLR re-bootstrap mid-run (e.g. P3.7's late-
    /// boot recovery test), not just for the initial
    /// chain bring-up.
    pub fn schedule_initial_steps(&mut self, boot_offsets: &[u64]) {
        assert_eq!(
            boot_offsets.len(),
            self.cores.len(),
            "boot_offsets length must match number of cores"
        );
        // Drop any pre-existing events so a re-bootstrap
        // doesn't fire stale events at outdated ticks.
        self.events = EventQueue::new();
        // Reset per-core cycle counters so subsequent
        // schedule_next_core_step computations are
        // relative to this fresh epoch.  Memory / stack /
        // peripheral state is left to the caller (typically
        // `apply_reset_all` precedes this).
        for core in self.cores.iter_mut() {
            core.reset_cycles_for_test();
        }
        // Reset the universal-clock head so step_ticks(N)
        // advances from the new epoch rather than carrying
        // pre-reset history forward.
        self.current_tick = 0;
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

    /// Regression: re-bootstrap mid-run drops stale events
    /// and resets cycle counters so the new boot epoch
    /// arithmetic is correct.  Without the fix, the queue
    /// would carry pre-MCLR events and the per-core
    /// cycles counter would keep its pre-reset value,
    /// causing schedule_next_core_step to compute ticks
    /// relative to a stale epoch.
    #[test]
    fn schedule_initial_steps_drops_stale_events_and_resets_cycles() {
        let mut chain = Chain::new();
        let mut core = Core::new(Variant::Pic18F25K20);
        core.flash_mut().copy_from_slice(&build_self_loop_flash());
        let idx = chain.push_core(core);
        chain.apply_reset_all(ResetSource::PowerOn);
        chain.schedule_initial_steps(&[0]);
        // Run 1000 ticks to accumulate cycles + queue
        // state.
        chain.step_ticks(1000);
        assert!(chain.cores[idx].cycles() > 0);
        assert!(chain.events.len() > 0);

        // Re-bootstrap (simulating MCLR + new epoch).
        chain.apply_reset_all(ResetSource::Mclr);
        chain.schedule_initial_steps(&[2000]);

        // Cycles reset; queue holds exactly one new event
        // at tick 2000; current_tick reset.
        assert_eq!(chain.cores[idx].cycles(), 0);
        assert_eq!(chain.events.len(), 1);
        assert_eq!(chain.current_tick, 0);
        assert_eq!(chain.boot_epochs[idx], 2000);
    }

    /// End-to-end UART chain: source core transmits a
    /// byte; chain dispatch propagates it to the wired
    /// destination core's EUSART RX (RCREG + RCIF).
    #[test]
    fn uart_byte_propagates_from_src_tx_to_dst_rx() {
        // Build a flash that runs the V1.71 EUSART setup
        // + a TXREG=0x55 write, then loops on BRA -1.
        // Reuse the existing peripheral_eusart_parity
        // demo encoding inline here -- 11 setup
        // instructions + a 960-Tcy frame on the source.
        let mut flash_src = vec![0u8; 32 * 1024];
        let prog: &[(u32, [u8; 2])] = &[
            (0x0000, [0x05, 0x0E]),       // MOVLW 0x05
            (0x0002, [0xAF, 0x6E]),       // MOVWF SPBRG (a=0)
            (0x0004, [0x20, 0x0E]),       // MOVLW 0x20 (TXEN)
            (0x0006, [0xAC, 0x6E]),       // MOVWF TXSTA
            (0x0008, [0x80, 0x0E]),       // MOVLW 0x80 (SPEN)
            (0x000A, [0xAB, 0x6E]),       // MOVWF RCSTA
            (0x000C, [0x40, 0x0E]),       // MOVLW 0x40
            (0x000E, [0xB8, 0x6E]),       // MOVWF BAUDCON
            (0x0010, [0x55, 0x0E]),       // MOVLW 0x55
            (0x0012, [0xAD, 0x6E]),       // MOVWF TXREG
            (0x0014, [0xFF, 0xD7]),       // BRA -1
        ];
        for (a, bytes) in prog {
            flash_src[*a as usize] = bytes[0];
            flash_src[*a as usize + 1] = bytes[1];
        }
        // Destination flash: enable RX (SPEN | CREN) then
        // BRA loop.
        let mut flash_dst = vec![0u8; 32 * 1024];
        let dst_prog: &[(u32, [u8; 2])] = &[
            (0x0000, [0x90, 0x0E]),       // MOVLW 0x90 (SPEN|CREN)
            (0x0002, [0xAB, 0x6E]),       // MOVWF RCSTA
            (0x0004, [0xFF, 0xD7]),       // BRA -1
        ];
        for (a, bytes) in dst_prog {
            flash_dst[*a as usize] = bytes[0];
            flash_dst[*a as usize + 1] = bytes[1];
        }

        let mut chain = Chain::new();
        let mut src = Core::new(Variant::Pic18F25K20);
        src.flash_mut().copy_from_slice(&flash_src);
        let i_src = chain.push_core(src);
        let mut dst = Core::new(Variant::Pic18F25K20);
        dst.flash_mut().copy_from_slice(&flash_dst);
        let i_dst = chain.push_core(dst);
        chain.couple_uart(
            i_src,
            crate::pinnet::default_tx_pin(),
            i_dst,
            crate::pinnet::default_rx_pin(),
        );
        chain.apply_reset_all(ResetSource::PowerOn);
        chain.schedule_initial_steps(&[0, 0]);

        // Step long enough for both cores to set up + the
        // 960-Tcy frame to drain.  K20 setup ~11 cycles =
        // 11 * 16 = 176 ticks; frame = 960 Tcy = 15360
        // ticks.  Give it 30 000.
        chain.step_ticks(30_000);

        // Destination's RCREG should hold 0x55.
        let rcreg = chain.cores[i_dst].memory.read_raw(
            crate::memory::Address::from_raw(0xFAE),
        );
        assert_eq!(rcreg, 0x55, "destination RCREG must hold the propagated byte");
        // PIR1.RCIF (bit 5) must be set.
        let pir1 = chain.cores[i_dst].memory.read_raw(
            crate::memory::Address::from_raw(0xF9E),
        );
        assert_eq!(pir1 & (1 << 5), 1 << 5, "destination RCIF must assert");
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
