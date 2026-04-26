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

use crate::core::Core;
use crate::peripherals::osc;
use crate::scheduler::{Event, EventKind, EventQueue};

/// Multi-core chain on a single universal-clock timeline.
pub struct Chain {
    /// Cores in firmware-deterministic order.  Index into
    /// this vec is the `core_idx` carried in event kinds.
    pub cores: Vec<Core>,
    /// Universal-clock tick at the head of the queue
    /// (= `cores[i].cycles * ticks_per_tcy(variant_i)` for
    /// each core when fully sync'd).  Phase-3 sub-tasks
    /// will use this to bridge per-core Tcy counters to
    /// the global tick.
    pub current_tick: u64,
    /// Global event queue.  Future P3.x sub-tasks post
    /// pin-propagation, peripheral deadlines, etc. here.
    pub events: EventQueue,
}

impl Chain {
    /// Construct an empty chain with no cores.  Callers
    /// `push_core` to add CONTROL + MAINs in firmware
    /// order.
    pub fn new() -> Self {
        Chain {
            cores: Vec::new(),
            current_tick: 0,
            events: EventQueue::new(),
        }
    }

    /// Add a core to the chain.  Returns the core's index.
    pub fn push_core(&mut self, core: Core) -> usize {
        let idx = self.cores.len();
        self.cores.push(core);
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

    /// Phase-3 stub: every event fired during this skeleton
    /// is a no-op.  P3.2-P3.7 will plumb actual handlers
    /// (instruction step on `CoreInstructionComplete`, pin
    /// propagation on `PinPropagation`, peripheral deadline
    /// dispatch).
    fn dispatch_event(&mut self, _event: Event) {
        // Intentional no-op for P3.1 skeleton.
    }

    /// Schedule a `CoreInstructionComplete` event for the
    /// given core at its next instruction-complete tick,
    /// derived from the core's current Tcy count + ticks-
    /// per-Tcy.  Phase-3 sub-tasks will call this after
    /// each instruction step.
    pub fn schedule_next_core_step(&mut self, core_idx: usize) {
        let tcy = self.cores[core_idx].cycles();
        let factor = self.ticks_per_tcy(core_idx) as u64;
        let tick = tcy.saturating_mul(factor);
        self.events
            .push(tick, EventKind::CoreInstructionComplete(core_idx));
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
}
