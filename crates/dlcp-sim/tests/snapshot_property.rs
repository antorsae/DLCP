//! Phase 5 (P5.2) property-based tests for the snapshot/restore
//! round-trip in `dlcp_sim::snapshot`.
//!
//! Strategy: generate a stimulus stream (ticks + reset injections)
//! against a fresh `Chain`, then assert
//! `restore(snapshot(c)) == c` byte-stably for every reachable
//! state.  We don't construct random `Chain` graphs from scratch
//! because the chain has many cross-field invariants (event-queue
//! ordering, pin-coupling indices, etc.) that proptest's blind
//! struct-generation can't preserve; reaching states by stimulus
//! is closer to how the simulator is exercised in practice.
//!
//! For an empty single-CPU-state chain, the byte-stable round-trip
//! gate boils down to: every `Vec<...>` field round-trips with the
//! same length+contents, every `Option<...>` round-trips with the
//! same Some/None, every `BinaryHeap` round-trips with the same
//! internal layout (serde serializes in iteration order; std's
//! `BinaryHeap::from(Vec)` re-heapifies, but a heap-ordered Vec
//! re-serializes identically without re-sift).
//!
//! Spec reference: `docs/SIM_REWRITE_RUST_SPEC.md` §9 P5.2.

use dlcp_sim::chain::Chain;
use dlcp_sim::snapshot::{decode, encode};
use proptest::prelude::*;

#[derive(Clone, Debug)]
enum Stimulus {
    /// Advance the universal clock by N ticks.
    StepTicks(u64),
    /// Toggle the chain-wide UART blackout (drops every byte
    /// either direction during blackout).
    SetBlackout(bool),
}

fn stimulus_strategy() -> impl Strategy<Value = Stimulus> {
    prop_oneof![
        (0u64..=2_000_000u64).prop_map(Stimulus::StepTicks),
        any::<bool>().prop_map(Stimulus::SetBlackout),
    ]
}

fn stimulus_seq_strategy() -> impl Strategy<Value = Vec<Stimulus>> {
    proptest::collection::vec(stimulus_strategy(), 0..8)
}

fn apply(chain: &mut Chain, stim: &Stimulus) {
    match stim {
        Stimulus::StepTicks(n) => chain.step_ticks(*n),
        Stimulus::SetBlackout(b) => chain.set_uart_blackout(*b),
    }
}

proptest! {
    #![proptest_config(ProptestConfig {
        cases: 64,
        ..ProptestConfig::default()
    })]

    /// For every fuzzed stimulus stream applied to a fresh empty
    /// chain, `restore(snapshot(c))` must byte-equal `snapshot(c)`.
    #[test]
    fn snapshot_round_trip_byte_stable_under_stimulus(
        stims in stimulus_seq_strategy()
    ) {
        let mut chain = Chain::new();
        for s in &stims {
            apply(&mut chain, s);
        }
        let bytes = encode(&chain);
        let restored = decode(&bytes).expect("decode succeeds");
        let bytes2 = encode(&restored);
        prop_assert_eq!(bytes, bytes2);
    }

    /// Snapshots must be deterministic: encoding the same chain
    /// twice produces identical bytes.  Catches non-determinism
    /// from stray HashMap/HashSet iteration order if any sneaks
    /// into the chain's reachable graph in the future.
    #[test]
    fn snapshot_is_deterministic(stims in stimulus_seq_strategy()) {
        let mut chain = Chain::new();
        for s in &stims {
            apply(&mut chain, s);
        }
        let a = encode(&chain);
        let b = encode(&chain);
        prop_assert_eq!(a, b);
    }

    /// Two chains that received identical stimulus streams snapshot
    /// to identical bytes.  Catches "spooky non-determinism" --
    /// i.e. a hidden dependency on something that's not in the
    /// stimulus stream (system clock, ProcessId, etc.).
    #[test]
    fn replay_two_chains_produce_equal_snapshots(
        stims in stimulus_seq_strategy()
    ) {
        let mut a = Chain::new();
        let mut b = Chain::new();
        for s in &stims {
            apply(&mut a, s);
            apply(&mut b, s);
        }
        prop_assert_eq!(encode(&a), encode(&b));
    }
}
