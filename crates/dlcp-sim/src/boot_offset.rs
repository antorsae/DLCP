//! Boot-offset specification — when each core's first
//! instruction-complete event lands on the universal-clock
//! timeline.
//!
//! ## Spec §7 scenarios
//!
//! 1. CONTROL + MAIN0 powered by the same PSU: both come
//!    out of POR within a few microseconds of each other.
//!    Modeled by `BootOffsetSpec::Fixed { ticks: 0 }` for
//!    both, or a small fixed offset (~30k ticks ≈ 0.6 ms
//!    at 48 MHz) to capture POR-timer skew.
//! 2. MAIN1 powered by a separate PSU: comes out of POR
//!    significantly later (or earlier) than the first
//!    PSU's boot, sometimes 1.5 s or more.  Modeled by
//!    `BootOffsetSpec::Fixed { ticks: 72_000_000 }` for
//!    the explicit 1.5 s case the spec calls out, or
//!    `RangedRandom { min, max, seed }` for soak coverage.
//! 3. Late-boot recovery: MAIN1 boots after CONTROL has
//!    already started polling.  P3.7 exercises this.
//!
//! ## Determinism
//!
//! `RangedRandom` uses a xorshift64 PRNG seeded by
//! `(seed, core_idx)` so a given chain configuration
//! produces identical boot offsets across runs.  Phase-5
//! soak tests can iterate the seed to enumerate the
//! offset space deterministically.

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BootOffsetSpec {
    /// Exact universal-tick offset.  0 means the core
    /// starts at tick 0 (alongside any other Fixed-0
    /// cores).
    Fixed { ticks: u64 },
    /// Deterministic random offset within
    /// `[min_ticks, max_ticks]`.  The xorshift64 PRNG is
    /// seeded by `(seed, core_idx)` so different cores in
    /// the same chain get different offsets, and the same
    /// (seed, core_idx) pair across runs produces the
    /// same offset.
    RangedRandom {
        min_ticks: u64,
        max_ticks: u64,
        seed: u64,
    },
}

impl BootOffsetSpec {
    /// Resolve the spec to a concrete tick offset for the
    /// given `core_idx` in the chain.
    pub fn resolve(&self, core_idx: usize) -> u64 {
        match *self {
            BootOffsetSpec::Fixed { ticks } => ticks,
            BootOffsetSpec::RangedRandom {
                min_ticks,
                max_ticks,
                seed,
            } => {
                assert!(
                    min_ticks <= max_ticks,
                    "BootOffsetSpec::RangedRandom: min_ticks ({min_ticks}) must be <= max_ticks ({max_ticks})"
                );
                let mut state = mix_seed(seed, core_idx as u64);
                state = xorshift64(state);
                if min_ticks == max_ticks {
                    return min_ticks;
                }
                let span = max_ticks - min_ticks + 1;
                min_ticks + (state % span)
            }
        }
    }
}

/// Mix a (seed, core_idx) pair into a single 64-bit state
/// for the PRNG.  Splitmix64-style finalizer; adequate for
/// non-cryptographic determinism.
fn mix_seed(seed: u64, core_idx: u64) -> u64 {
    let mut z = seed.wrapping_add(core_idx).wrapping_add(0x9E3779B97F4A7C15);
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58476D1CE4E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D049BB133111EB);
    z ^ (z >> 31)
}

/// Standard xorshift64 step.  Produces a sequence of
/// pseudo-random 64-bit values from a non-zero seed.
fn xorshift64(state: u64) -> u64 {
    let mut x = if state == 0 { 1 } else { state };
    x ^= x << 13;
    x ^= x >> 7;
    x ^= x << 17;
    x
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fixed_zero_returns_zero() {
        let spec = BootOffsetSpec::Fixed { ticks: 0 };
        assert_eq!(spec.resolve(0), 0);
        assert_eq!(spec.resolve(1), 0);
    }

    #[test]
    fn fixed_nonzero_returns_same_for_all_cores() {
        let spec = BootOffsetSpec::Fixed { ticks: 72_000_000 };
        for core_idx in 0..5 {
            assert_eq!(spec.resolve(core_idx), 72_000_000);
        }
    }

    #[test]
    fn ranged_random_within_bounds() {
        let spec = BootOffsetSpec::RangedRandom {
            min_ticks: 1000,
            max_ticks: 2000,
            seed: 42,
        };
        for core_idx in 0..10 {
            let r = spec.resolve(core_idx);
            assert!(
                (1000..=2000).contains(&r),
                "core {core_idx} -> {r} out of [1000, 2000]"
            );
        }
    }

    #[test]
    fn ranged_random_deterministic_per_seed_and_core_idx() {
        let spec = BootOffsetSpec::RangedRandom {
            min_ticks: 0,
            max_ticks: 1_000_000,
            seed: 0xCAFEBABE,
        };
        // Same (seed, core_idx) -> same value across calls.
        let a0 = spec.resolve(0);
        let a0b = spec.resolve(0);
        let a1 = spec.resolve(1);
        let a1b = spec.resolve(1);
        assert_eq!(a0, a0b);
        assert_eq!(a1, a1b);
        // Different core_idx -> different value (xorshift +
        // mix_seed make collisions astronomically rare for
        // small ranges -> `assert_ne!` is fine here).
        assert_ne!(a0, a1);
    }

    #[test]
    fn ranged_random_different_seed_different_value() {
        let core_idx = 0;
        let a = BootOffsetSpec::RangedRandom {
            min_ticks: 0,
            max_ticks: 1_000_000,
            seed: 1,
        }
        .resolve(core_idx);
        let b = BootOffsetSpec::RangedRandom {
            min_ticks: 0,
            max_ticks: 1_000_000,
            seed: 2,
        }
        .resolve(core_idx);
        assert_ne!(a, b);
    }

    #[test]
    fn ranged_random_min_equals_max_returns_that_value() {
        let spec = BootOffsetSpec::RangedRandom {
            min_ticks: 500,
            max_ticks: 500,
            seed: 99,
        };
        assert_eq!(spec.resolve(0), 500);
        assert_eq!(spec.resolve(1), 500);
    }

    #[test]
    #[should_panic(expected = "min_ticks")]
    fn ranged_random_min_greater_than_max_panics() {
        let spec = BootOffsetSpec::RangedRandom {
            min_ticks: 1000,
            max_ticks: 500,
            seed: 1,
        };
        let _ = spec.resolve(0);
    }
}
