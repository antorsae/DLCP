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
    /// `|drift_ppm| > MAX_DRIFT_PPM`.  Uses `unsigned_abs`
    /// to avoid the `i32::MIN.abs()` wrap-overflow case.
    pub fn with_drift_ppm(variant: Variant, drift_ppm: i32) -> Self {
        assert!(
            drift_ppm.unsigned_abs() <= MAX_DRIFT_PPM as u32,
            "drift_ppm {drift_ppm} out of range; max {MAX_DRIFT_PPM}"
        );
        ClockDomain {
            nominal_ticks_per_tcy: osc::ticks_per_tcy(variant),
            drift_ppm,
        }
    }

    /// Apply the configured drift to a nominal tick count.
    /// Returns `nominal * (1 + drift_ppm * 1e-6)` rounded
    /// to nearest integer (ties away from zero), saturating
    /// at u64 boundaries.
    ///
    /// Implementation: compute the full
    /// `nominal * (1_000_000 + drift_ppm)` product in i128
    /// (which never overflows since both factors fit in
    /// 64 bits and the product is at most 2^64 * 1.1e6 <
    /// 2^85), then bias by ±500_000 in the *result*
    /// direction (positive scaled -> +500_000, negative
    /// scaled -> -500_000) before dividing by 1_000_000.
    /// This gives correct round-to-nearest-away-from-zero
    /// for both positive and negative drift, including
    /// half-integer ties.
    pub fn apply_drift(&self, nominal_ticks: u64) -> u64 {
        if self.drift_ppm == 0 {
            return nominal_ticks;
        }
        let nominal_i = nominal_ticks as i128;
        let scale_total = 1_000_000_i128 + self.drift_ppm as i128;
        let scaled = nominal_i * scale_total;
        let bias = if scaled >= 0 { 500_000 } else { -500_000 };
        let result_i = (scaled + bias) / 1_000_000;
        if result_i < 0 {
            0
        } else if result_i > u64::MAX as i128 {
            u64::MAX
        } else {
            result_i as u64
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
        // 1234 nominal × +1500 ppm.  scaled = 1234 *
        // 1_001_500 = 1_235_851_000.  bias +500_000 ->
        // 1_236_351_000 / 1_000_000 = 1236.  ✓
        let d = ClockDomain::with_drift_ppm(Variant::Pic18F25K20, 1500);
        assert_eq!(d.apply_drift(1234), 1236);
    }

    /// Half-integer tie at negative drift rounds AWAY from
    /// zero (= "up" since result is positive).  500_000
    /// nominal × -1 ppm = 499_999.5 -> 500_000.
    #[test]
    fn drift_round_to_nearest_negative_half_tie() {
        let d = ClockDomain::with_drift_ppm(Variant::Pic18F25K20, -1);
        assert_eq!(d.apply_drift(500_000), 500_000);
    }

    /// Half-integer tie at positive drift also rounds away
    /// from zero.  500_000 × +1 ppm = 500_000.5 -> 500_001.
    #[test]
    fn drift_round_to_nearest_positive_half_tie() {
        let d = ClockDomain::with_drift_ppm(Variant::Pic18F25K20, 1);
        assert_eq!(d.apply_drift(500_000), 500_001);
    }

    /// `i32::MIN.abs()` wraps to `i32::MIN` in release; the
    /// guard must reject it without panicking on overflow.
    #[test]
    #[should_panic(expected = "out of range")]
    fn drift_i32_min_panics_via_unsigned_abs_guard() {
        let _ = ClockDomain::with_drift_ppm(
            Variant::Pic18F25K20,
            i32::MIN,
        );
    }
}
