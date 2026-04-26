//! Per-core clock domain — `ticks_per_tcy` plus an
//! optional drift in parts-per-million.
//!
//! ## Phase-3.3 scope
//!
//! Wraps the variant-derived `peripherals::osc::ticks_per_tcy`
//! into a per-core struct that also carries an optional
//! `drift_ppm`.  Phase-3.5 multicore parity work uses this
//! to model the documented HFINTOSC tolerance (±2% per
//! DS40001303H §26.2 / DS39632E §27.2): two cores spec'd
//! at the same nominal Fosc may drift apart at runtime,
//! which is why `wire_chain_gpsim.py` had to apply skid
//! correction.  The Rust simulator captures the drift up-
//! front so the chain scheduler can advance each core by
//! the per-core drifted-tick count -- no post-hoc skid.
//!
//! Drift convention: `drift_ppm > 0` means the core's
//! Tcy takes MORE universal ticks than nominal (slower
//! clock); `drift_ppm < 0` means fewer ticks (faster).
//! Range: ±100 000 ppm (±10 %) covers any realistic
//! HFINTOSC variation; outside that the model panics on
//! construction so test typos don't silently accept
//! pathological values.

use crate::memory::Variant;
use crate::peripherals::osc;

/// Maximum |drift_ppm| accepted at construction.  10 %
/// covers any realistic HFINTOSC tolerance plus a safety
/// margin for Phase-4 fuzz tests.
pub const MAX_DRIFT_PPM: i32 = 100_000;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ClockDomain {
    /// Universal-clock ticks per Tcy (instruction cycle).
    /// Set from `osc::ticks_per_tcy(variant)` at
    /// construction.
    pub nominal_ticks_per_tcy: u32,
    /// Drift in parts per million.  0 = exact nominal;
    /// +ppm = slower (more ticks per Tcy); -ppm = faster.
    pub drift_ppm: i32,
}

impl ClockDomain {
    /// Construct a domain at the variant's nominal clock,
    /// no drift.
    pub fn new(variant: Variant) -> Self {
        ClockDomain {
            nominal_ticks_per_tcy: osc::ticks_per_tcy(variant),
            drift_ppm: 0,
        }
    }

    /// Construct a domain at the variant's nominal clock
    /// with a `drift_ppm` offset.  Panics if
    /// `|drift_ppm| > MAX_DRIFT_PPM`.
    pub fn with_drift_ppm(variant: Variant, drift_ppm: i32) -> Self {
        assert!(
            drift_ppm.abs() <= MAX_DRIFT_PPM,
            "drift_ppm {drift_ppm} out of range; max {MAX_DRIFT_PPM}"
        );
        ClockDomain {
            nominal_ticks_per_tcy: osc::ticks_per_tcy(variant),
            drift_ppm,
        }
    }

    /// Apply the configured drift to a nominal tick count.
    /// Returns `nominal * (1 + drift_ppm * 1e-6)` rounded
    /// to nearest integer (saturating at u64 boundaries).
    pub fn apply_drift(&self, nominal_ticks: u64) -> u64 {
        if self.drift_ppm == 0 {
            return nominal_ticks;
        }
        // Compute as i128 to avoid overflow on the
        // intermediate product.  ppm scale is 1e-6 so we
        // multiply by drift_ppm then divide by 1_000_000;
        // round-to-nearest by adding +500_000 (or
        // -500_000 for negative drift) before the divide.
        let nominal_i = nominal_ticks as i128;
        let scale_i = self.drift_ppm as i128;
        let bias = if scale_i >= 0 { 500_000 } else { -500_000 };
        let adjustment_num = nominal_i * scale_i + bias;
        let adjustment = adjustment_num / 1_000_000;
        let result = nominal_i + adjustment;
        if result < 0 {
            0
        } else if result > u64::MAX as i128 {
            u64::MAX
        } else {
            result as u64
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn k20_default_no_drift() {
        let d = ClockDomain::new(Variant::Pic18F25K20);
        assert_eq!(d.nominal_ticks_per_tcy, 16);
        assert_eq!(d.drift_ppm, 0);
        assert_eq!(d.apply_drift(1000), 1000);
    }

    #[test]
    fn pic2455_default_no_drift() {
        let d = ClockDomain::new(Variant::Pic18F2455);
        assert_eq!(d.nominal_ticks_per_tcy, 12);
        assert_eq!(d.drift_ppm, 0);
        assert_eq!(d.apply_drift(1000), 1000);
    }

    #[test]
    fn drift_plus_1_percent_slows_by_1_percent() {
        let d = ClockDomain::with_drift_ppm(Variant::Pic18F25K20, 10_000);
        // 10 000 ppm = 1 %; 1_000_000 nominal ticks ->
        // 1_010_000 drifted.
        assert_eq!(d.apply_drift(1_000_000), 1_010_000);
    }

    #[test]
    fn drift_minus_1_percent_speeds_up_by_1_percent() {
        let d = ClockDomain::with_drift_ppm(Variant::Pic18F25K20, -10_000);
        assert_eq!(d.apply_drift(1_000_000), 990_000);
    }

    #[test]
    fn drift_zero_returns_nominal() {
        let d = ClockDomain::with_drift_ppm(Variant::Pic18F25K20, 0);
        for n in [0, 1, 100, 1_000_000_000_u64] {
            assert_eq!(d.apply_drift(n), n);
        }
    }

    #[test]
    fn drift_2_percent_matches_documented_hfintosc_tolerance() {
        // DS40001303H §26.2 lists ±2 % HFINTOSC accuracy.
        // 20 000 ppm on 1 second = 0.02 s -> 20 000 µs.
        let d = ClockDomain::with_drift_ppm(Variant::Pic18F25K20, 20_000);
        // 1 000 000 nominal ticks -> 1 020 000 drifted.
        assert_eq!(d.apply_drift(1_000_000), 1_020_000);
    }

    #[test]
    #[should_panic(expected = "out of range")]
    fn drift_above_max_panics() {
        let _ = ClockDomain::with_drift_ppm(
            Variant::Pic18F25K20,
            MAX_DRIFT_PPM + 1,
        );
    }

    #[test]
    fn drift_round_to_nearest_positive() {
        // 1234 nominal × 1500 ppm.  raw = 1234*1500 = 1_851_000.
        // bias +500_000 -> 2_351_000 / 1_000_000 = 2.
        // Result = 1234 + 2 = 1236.
        let d = ClockDomain::with_drift_ppm(Variant::Pic18F25K20, 1500);
        assert_eq!(d.apply_drift(1234), 1236);
    }
}
