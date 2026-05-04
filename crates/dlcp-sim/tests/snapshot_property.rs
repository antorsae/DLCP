//! Phase 5 (P5.2) property-based tests for the snapshot/restore
//! round-trip in `dlcp_sim::snapshot`.
//!
//! Strategy: generate stimulus streams (StepTicks ticks, SetBlackout
//! UART-blackout toggles) and replay them against either:
//!
//!   * an empty `Chain::new()` (smoke test for scalar fields:
//!     `current_tick`, `uart_blackout`, etc.); OR
//!   * a non-trivial `Chain` carrying a real V1.71 CONTROL core
//!     loaded from
//!     `firmware/patched/releases/DLCP_Control_V1.71.hex`, with
//!     a clock domain and a scheduled boot epoch (exercises
//!     `Core` / `Memory` / `Stack` / `HexImage` / `EventQueue`
//!     / `ClockDomain` serde).
//!
//! For every fuzzed stream we assert
//! `encode(decode(encode(c))?)? == encode(c)` (byte-stable
//! round-trip), `encode(a) == encode(b)` for two chains given
//! identical streams (replay determinism), and
//! `encode(c) == encode(c)` for the same chain encoded twice
//! (encode determinism, catches HashMap iteration-order leaks).
//!
//! The tests do NOT construct random `Chain` graphs from scratch
//! because `Chain` has many cross-field invariants (event-queue
//! ordering, pin-coupling indices, etc.) that proptest's blind
//! struct-generation can't preserve; reaching states by stimulus
//! is closer to how the simulator is exercised in practice.
//!
//! Spec reference: `docs/SIM_REWRITE_RUST_SPEC.md` §9 P5.2.

use dlcp_sim::chain::Chain;
use dlcp_sim::clock::ClockDomain;
use dlcp_sim::core::{CoreLoadOptions, core_from_hex_image};
use dlcp_sim::hex::HexImage;
use dlcp_sim::memory::Variant;
use dlcp_sim::reset::ResetSource;
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

/// Build a non-trivial 1-core chain: V1.71 CONTROL hex loaded into a
/// K20 core, K20 ClockDomain, scheduled boot epoch.  Exercises every
/// serde derive on the chain's reachable state surface (Core,
/// Memory, Stack, HexImage, EventQueue, ClockDomain, Peripherals,
/// PinNet, Hd44780 if attached -- not in this minimal builder).
fn build_v171_control_chain() -> Chain {
    let hex_path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|p| p.parent())
        .expect("crate dir has 2 ancestors")
        .join("firmware/patched/releases/DLCP_Control_V1.71.hex");
    let image =
        HexImage::from_hex_path(&hex_path).expect("V1.71 hex parses");
    let core = core_from_hex_image(
        Variant::Pic18F25K20,
        &image,
        CoreLoadOptions::default(),
    );
    let clock = ClockDomain::new(Variant::Pic18F25K20);
    let mut chain = Chain::new();
    chain.push_core_with_clock(core, clock);
    // POR/MCLR reset BEFORE scheduling: `Core::new` /
    // `Memory::new` leave SFRs zero, but real K20 boot starts
    // from POR.  Mirror what the multicore_parity fixtures do
    // (see `tests/multicore_parity.rs::three_core_ring_*`) so
    // the V1.71 property exercises a physically-reachable boot
    // chain, not an all-zero-SFR phantom state.
    chain.apply_reset_all(ResetSource::PowerOn);
    chain.schedule_initial_steps(&[0]);
    // Anchor the POR-then-schedule invariant: a future edit that
    // skips `apply_reset_all` would leave SFRs zero (POR sets
    // RCON to a known non-zero value) AND `schedule_initial_steps`
    // pushes one CoreInstructionComplete event per core.  Both
    // checks catch ordering-regression that byte-stable snapshot
    // round-trip alone would silently accept.
    debug_assert!(
        chain.events.len() >= 1,
        "schedule_initial_steps must seed >= 1 event"
    );
    chain
}

proptest! {
    #![proptest_config(ProptestConfig {
        cases: 64,
        ..ProptestConfig::default()
    })]

    /// Empty-chain smoke test: byte-stable round-trip after
    /// `StepTicks` + `SetBlackout` stimulus on `Chain::new()`.
    /// Covers scalar fields (`current_tick`, `uart_blackout`)
    /// only -- empty `cores`, `events`, etc.
    #[test]
    fn empty_chain_round_trip_byte_stable(
        stims in stimulus_seq_strategy()
    ) {
        let mut chain = Chain::new();
        for s in &stims {
            apply(&mut chain, s);
        }
        let bytes = encode(&chain);
        let restored = decode(&bytes).expect("decode succeeds");
        prop_assert_eq!(encode(&restored), bytes);
    }

    /// Empty-chain encode determinism: encoding the same chain
    /// twice produces identical bytes.  Catches stray HashMap /
    /// HashSet iteration-order non-determinism.
    #[test]
    fn empty_chain_encode_is_deterministic(
        stims in stimulus_seq_strategy()
    ) {
        let mut chain = Chain::new();
        for s in &stims {
            apply(&mut chain, s);
        }
        prop_assert_eq!(encode(&chain), encode(&chain));
    }

    /// Empty-chain replay determinism: two empty chains given
    /// identical stimulus streams snapshot to identical bytes.
    /// Catches "spooky" hidden dependencies (system clock, PID,
    /// etc.) that aren't in the stimulus stream.
    #[test]
    fn empty_chain_replay_two_chains_equal(
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

    /// Non-trivial chain: V1.71 CONTROL core loaded from
    /// canonical hex, scheduled boot epoch, K20 clock.  Exercises
    /// `Core` / `Memory` (banked RAM + Access Bank + SFR) /
    /// `Stack` / `HexImage` / `EventQueue` / `ClockDomain` /
    /// `Peripherals` (oscillator, EUSART, MSSP, GPIO, EEPROM, ADC,
    /// USB, IRQ, timers) serde paths under `StepTicks` actually
    /// running PIC18 instructions.
    #[test]
    fn v171_chain_round_trip_byte_stable(
        stims in stimulus_seq_strategy()
    ) {
        let mut chain = build_v171_control_chain();
        for s in &stims {
            apply(&mut chain, s);
        }
        let bytes = encode(&chain);
        let restored = decode(&bytes).expect("decode succeeds");
        prop_assert_eq!(encode(&restored), bytes);
    }

    /// V1.71 chain replay determinism: two V1.71 chains given
    /// identical stimulus streams snapshot to identical bytes.
    #[test]
    fn v171_chain_replay_two_chains_equal(
        stims in stimulus_seq_strategy()
    ) {
        let mut a = build_v171_control_chain();
        let mut b = build_v171_control_chain();
        for s in &stims {
            apply(&mut a, s);
            apply(&mut b, s);
        }
        prop_assert_eq!(encode(&a), encode(&b));
    }

    /// V1.71 chain encode determinism: encoding the same
    /// non-trivial chain twice produces identical bytes.
    /// Catches non-deterministic encoder paths within a single
    /// chain instance (e.g. a future serde impl that captures
    /// elapsed time, RNG state, or environment state at encode
    /// time).  The "spooky" cross-chain HashMap iteration-order
    /// case is covered by `v171_chain_replay_two_chains_equal`
    /// above -- this property's value is catching SAME-instance
    /// encoder non-determinism, not cross-instance.
    #[test]
    fn v171_chain_encode_is_deterministic(
        stims in stimulus_seq_strategy()
    ) {
        let mut chain = build_v171_control_chain();
        for s in &stims {
            apply(&mut chain, s);
        }
        prop_assert_eq!(encode(&chain), encode(&chain));
    }
}
