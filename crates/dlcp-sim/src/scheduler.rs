//! Global event queue (min-heap) for the multi-core
//! universal-clock scheduler.
//!
//! Each core's "next instruction-complete" event lives in
//! this queue, keyed by absolute universal-clock tick.
//! Pin-network propagation events (Phase 3.2) and timer
//! deadline events (Phase 3.3+) post into the same queue.
//!
//! ## Tick math
//!
//! The universal clock is 48 MHz (LCM of CONTROL's 12 MHz
//! and MAIN's 16 MHz Fosc).  Each core advances by an
//! integer multiple of its `ticks_per_tcy`:
//!   * K20 CONTROL: 16 ticks/Tcy (3 MIPS Tcy)
//!   * 2455 MAIN:   12 ticks/Tcy (4 MIPS Tcy)
//! See `peripherals/osc.rs::ticks_per_tcy`.
//!
//! ## Phase-3 scope
//!
//! P3.1 lands the queue surface only; cross-core wiring,
//! pin propagation, and chain-step semantics build on top
//! of it through P3.2-P3.7.

use std::cmp::Ordering;
use std::collections::BinaryHeap;

/// What an event's owner is.  Phase-3 distinguishes by
/// callback target rather than by core id directly --
/// pin-network events fire on neither core.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub enum EventKind {
    /// A core's next instruction completes at the
    /// scheduled tick.  Carries the core's index in the
    /// chain's `cores` vector.
    CoreInstructionComplete(usize),
    /// A pin-network propagation event (Phase 3.2).
    /// Carries an opaque ID resolved by the pin net.
    PinPropagation(u32),
    /// A peripheral-internal deadline (timer overflow,
    /// EEPROM write completion, ADC conversion done, etc.)
    /// scheduled by a peripheral via the queue.  Carries
    /// the core index + an opaque peripheral cookie.
    PeripheralDeadline { core_idx: usize, cookie: u32 },
}

/// One scheduled event in the global queue.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Event {
    /// Absolute universal-clock tick at which this event
    /// fires.
    pub tick: u64,
    /// Tie-break sequence number for events scheduled at
    /// the same tick.  Lower = earlier.  Each scheduler
    /// step bumps the next sequence id by 1, so events
    /// keep deterministic ordering.
    pub seq: u64,
    /// What kind of event this is.
    pub kind: EventKind,
}

/// Min-heap ordering: earlier `tick` first; on ties,
/// earlier `seq` first; final tie-break by `kind` (so the
/// `Ord` total order is consistent with the derived `Eq`
/// implementation -- two `Event` values are `Eq` only when
/// every field matches, so the order must distinguish them
/// when `tick` + `seq` collide).  In practice `EventQueue`
/// hands out monotonically-increasing `seq` values so the
/// kind-tie path is unreachable, but defining the order
/// totally avoids violating the `Ord`/`Eq` contract for
/// directly-constructed `Event` values that callers may
/// (e.g.) clone and compare manually.  `BinaryHeap` is a
/// max-heap, so invert.
impl Ord for Event {
    fn cmp(&self, other: &Self) -> Ordering {
        // Primary: earlier tick first.
        other
            .tick
            .cmp(&self.tick)
            .then_with(|| other.seq.cmp(&self.seq))
            // Final tie-break: discriminant order on the
            // EventKind variants.  Stable across runs because
            // we use the variant index, not the payload.
            .then_with(|| {
                kind_discriminant(&other.kind)
                    .cmp(&kind_discriminant(&self.kind))
            })
    }
}

impl PartialOrd for Event {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

/// Stable variant-discriminant for tie-break.  Used only
/// when two `Event`s share `tick` and `seq` -- by
/// construction `EventQueue::push` assigns unique seq, so
/// this path is dead in normal use.
fn kind_discriminant(k: &EventKind) -> u8 {
    match k {
        EventKind::CoreInstructionComplete(_) => 0,
        EventKind::PinPropagation(_) => 1,
        EventKind::PeripheralDeadline { .. } => 2,
    }
}

/// Global event queue.  Owns a monotonically-increasing
/// `next_seq` counter for tie-breaking.
#[derive(Default, Debug)]
pub struct EventQueue {
    heap: BinaryHeap<Event>,
    next_seq: u64,
}

impl EventQueue {
    pub fn new() -> Self {
        EventQueue::default()
    }

    /// Push a new event.  The caller supplies `tick` and
    /// `kind`; the queue assigns the tie-break `seq`.
    pub fn push(&mut self, tick: u64, kind: EventKind) {
        let event = Event {
            tick,
            seq: self.next_seq,
            kind,
        };
        self.next_seq += 1;
        self.heap.push(event);
    }

    /// Peek at the next event without consuming it.
    pub fn peek(&self) -> Option<&Event> {
        self.heap.peek()
    }

    /// Pop the next-firing event.
    pub fn pop(&mut self) -> Option<Event> {
        self.heap.pop()
    }

    /// True if no events are scheduled.
    pub fn is_empty(&self) -> bool {
        self.heap.is_empty()
    }

    /// Number of currently-scheduled events.
    pub fn len(&self) -> usize {
        self.heap.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_queue_pop_returns_none() {
        let mut q = EventQueue::new();
        assert!(q.is_empty());
        assert!(q.pop().is_none());
    }

    #[test]
    fn pushes_drain_in_tick_order() {
        let mut q = EventQueue::new();
        q.push(20, EventKind::CoreInstructionComplete(1));
        q.push(10, EventKind::CoreInstructionComplete(0));
        q.push(15, EventKind::CoreInstructionComplete(2));
        let a = q.pop().unwrap();
        let b = q.pop().unwrap();
        let c = q.pop().unwrap();
        assert_eq!(a.tick, 10);
        assert_eq!(b.tick, 15);
        assert_eq!(c.tick, 20);
    }

    #[test]
    fn ties_resolved_by_push_order_via_seq() {
        let mut q = EventQueue::new();
        q.push(50, EventKind::CoreInstructionComplete(0));
        q.push(50, EventKind::CoreInstructionComplete(1));
        q.push(50, EventKind::PinPropagation(42));
        let a = q.pop().unwrap();
        let b = q.pop().unwrap();
        let c = q.pop().unwrap();
        assert_eq!(a.kind, EventKind::CoreInstructionComplete(0));
        assert_eq!(b.kind, EventKind::CoreInstructionComplete(1));
        assert_eq!(c.kind, EventKind::PinPropagation(42));
    }

    #[test]
    fn peek_is_non_destructive() {
        let mut q = EventQueue::new();
        q.push(100, EventKind::PinPropagation(1));
        let p = q.peek().cloned();
        assert_eq!(p.unwrap().tick, 100);
        assert_eq!(q.len(), 1);
    }

    #[test]
    fn peripheral_deadline_event_drains_alongside_core_events() {
        let mut q = EventQueue::new();
        q.push(
            10,
            EventKind::CoreInstructionComplete(0),
        );
        q.push(
            5,
            EventKind::PeripheralDeadline {
                core_idx: 0,
                cookie: 0xDEAD,
            },
        );
        let first = q.pop().unwrap();
        match first.kind {
            EventKind::PeripheralDeadline { core_idx, cookie } => {
                assert_eq!(core_idx, 0);
                assert_eq!(cookie, 0xDEAD);
            }
            other => panic!("expected PeripheralDeadline, got {:?}", other),
        }
        assert_eq!(first.tick, 5);
    }
}
