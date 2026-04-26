//! Oscillator subsystem — Phase-2 stub.
//!
//! ## Scope
//!
//! Phase-2 ships:
//!   * `Osc::ticks_per_tcy(variant)` — universal-clock
//!     conversion factor.  CONTROL K20 runs at 12 MHz Fosc
//!     / 4 = 3 MIPS Tcy; MAIN 2455 runs at 16 MHz Fosc / 4
//!     = 4 MIPS Tcy.  On a 48 MHz universal clock (LCM of
//!     12 and 16): K20 = 16 ticks/Tcy, 2455 = 12 ticks/Tcy.
//!   * No-op `{reset_state, on_sfr_write, tick_tcy}` --
//!     OSCCON / OSCCON2 / OSCTUNE / RCON.IPEN POR values
//!     are handled by reset.rs's K20_POR table.
//!
//! Out of Phase-2 scope (deferred to Phase 3):
//!   * HFINTOSC settle delay (the `IOFS` / `OSTS` bit
//!     transitions firmware polls for after a clock-source
//!     change).
//!   * PLL ENABLE/READY state machine (the `PLLEN` bit and
//!     its 2 ms post-enable settle).
//!   * Two-speed clock-startup mode.
//!   * SCS<1:0> dynamic clock-source switching at runtime.
//!
//! These are time-driven behaviours that need the Phase-3
//! universal-clock scheduler to model accurately; the
//! firmware-visible OSCCON byte transitions are the only
//! thing the Phase-2 V1.71 parity test currently observes
//! and those are pinned in GPSIM_K20_DEVIATIONS.

use crate::memory::{Memory, Variant};

#[derive(Clone, Debug, Default)]
pub struct Osc;

impl Osc {
    pub fn new(_variant: Variant) -> Self {
        Osc
    }
    pub fn reset_state(&mut self) {}
    pub fn on_sfr_write(&mut self, _addr: u16, _value: u8, _mem: &mut Memory) {}
    pub fn tick_tcy(&mut self, _n: u32, _mem: &mut Memory) {}
}

/// Universal-clock conversion factor for the given variant.
/// Returns the number of 48 MHz universal clock ticks per
/// instruction cycle (Tcy).
///
///   * K20 (CONTROL): 12 MHz Fosc / 4 = 3 MHz Tcy.  On a
///     48 MHz universal clock: 48 / 3 = 16 ticks/Tcy.
///   * 2455 (MAIN):   16 MHz Fosc / 4 = 4 MHz Tcy.  On a
///     48 MHz universal clock: 48 / 4 = 12 ticks/Tcy.
///
/// Phase-3's chain scheduler reads this via the peripheral
/// surface to advance both cores by integer ticks every
/// scheduler step.
pub const fn ticks_per_tcy(variant: Variant) -> u32 {
    match variant {
        Variant::Pic18F25K20 => 16,
        Variant::Pic18F2455 => 12,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn k20_universal_factor_16() {
        assert_eq!(ticks_per_tcy(Variant::Pic18F25K20), 16);
    }

    #[test]
    fn pic2455_universal_factor_12() {
        assert_eq!(ticks_per_tcy(Variant::Pic18F2455), 12);
    }

    #[test]
    fn factors_share_lcm_48mhz() {
        // Sanity: both factors must divide 48 evenly so the
        // LCM-derived universal clock can address each
        // core's instruction boundary on an integer tick.
        assert_eq!(48 % ticks_per_tcy(Variant::Pic18F25K20), 0);
        assert_eq!(48 % ticks_per_tcy(Variant::Pic18F2455), 0);
    }

    #[test]
    fn no_op_lifecycle_does_not_panic() {
        let mut osc = Osc::new(Variant::Pic18F25K20);
        osc.reset_state();
        let mut mem = Memory::new(Variant::Pic18F25K20);
        osc.on_sfr_write(0xFD3, 0x40, &mut mem);
        osc.tick_tcy(1_000_000, &mut mem);
    }
}
