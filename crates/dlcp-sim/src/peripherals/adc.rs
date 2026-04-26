//! ADC peripheral — Phase-2 minimum-viable.
//!
//! ## Scope
//!
//! Used only by the V3.2 / V2.x MAIN firmware (2455).  The
//! AN0 channel samples the audio-input level; firmware
//! gates the standby-state machine on the result crossing
//! the documented 0x0236 / 0x0229 / 0x0228 thresholds (per
//! `tests/sim/test_main_gpsim_an0_boot.py`).  CONTROL (K20)
//! does not use the ADC in cycle-10 boot scope.
//!
//! ## Phase-2 model
//!
//! - ADCON0 / ADCON1 / ADCON2 SFRs tracked.
//! - GO/DONE bit (ADCON0 bit 1) triggers a conversion when
//!   set with ADON=1, edge-sensitive on the not-busy
//!   transition.  The Phase-2 model uses a fixed 12-Tcy
//!   conversion delay regardless of ADCON2.{ACQT, ADCS} --
//!   accurate Tacq + Tconv math is deferred to P2.7.  At
//!   completion: GO/DONE clears, ADIF (PIR1 bit 6) asserts,
//!   ADRESH:ADRESL loads the configured AN0 input value
//!   (test-injected).
//! - Mid-conversion writes that clear GO/DONE OR disable
//!   ADON abort the conversion (DS §21.6) -- ADRESH:ADRESL
//!   are NOT updated and ADIF stays low.
//! - Phase-2 has no analog pin network; tests inject the
//!   AN0 sample value via [`Adc::set_an0_sample`].  Phase-3
//!   pin network will route the sample from a virtual
//!   audio-source pin.

use crate::memory::{Address, Memory, Variant};

pub const ADCON0_ADDR: u16 = 0xFC2;
pub const ADCON1_ADDR: u16 = 0xFC1;
pub const ADCON2_ADDR: u16 = 0xFC0;
pub const ADRESH_ADDR: u16 = 0xFC4;
pub const ADRESL_ADDR: u16 = 0xFC3;
pub const PIR1_ADDR: u16 = 0xF9E;

const ADCON0_GODONE: u8 = 1 << 1;
const ADCON0_ADON: u8 = 1 << 0;
const ADCON2_ADFM: u8 = 1 << 7;
const PIR1_ADIF: u8 = 1 << 6;

#[derive(Clone, Debug, Default)]
pub struct Adc {
    /// AN0 input sample value (10-bit).  Defaults to 0;
    /// tests / Phase-3 pin network override via
    /// `set_an0_sample`.
    an0_sample: u16,
    /// Tcy remaining until the in-flight conversion
    /// completes.  `None` means no conversion in flight.
    pending_tcy: Option<u32>,
}

impl Adc {
    pub fn new(_variant: Variant) -> Self {
        Adc::default()
    }

    pub fn reset_state(&mut self) {
        self.pending_tcy = None;
        // an0_sample is a test-injected input, not silicon
        // state -- leave it intact across resets so a
        // synthetic boot sequence that sets the sample
        // before the first reset still sees it after.
    }

    /// Inject the analog AN0 sample value (0..=0x3FF) the
    /// next conversion should return.  Phase-3 pin network
    /// will replace this with a pin-driven path; for
    /// Phase-2 tests this is the only way to set the
    /// conversion result.
    pub fn set_an0_sample(&mut self, value_10bit: u16) {
        self.an0_sample = value_10bit & 0x3FF;
    }

    pub fn on_sfr_write(&mut self, addr: u16, value: u8, mem: &mut Memory) {
        match addr {
            ADCON0_ADDR => self.handle_adcon0_write(value, mem),
            ADCON1_ADDR | ADCON2_ADDR | ADRESH_ADDR | ADRESL_ADDR => {}
            _ => {}
        }
    }

    pub fn tick_tcy(&mut self, n: u32, mem: &mut Memory) {
        let Some(remaining) = self.pending_tcy else {
            return;
        };
        if n < remaining {
            self.pending_tcy = Some(remaining - n);
            return;
        }
        // Conversion complete.
        self.pending_tcy = None;
        let adfm = mem.read_raw(Address::from_raw(ADCON2_ADDR)) & ADCON2_ADFM != 0;
        // ADFM=1: right-justified (bits 9..0 in
        // ADRESH<1:0>:ADRESL).  ADFM=0: left-justified
        // (bits 9..0 in ADRESH<7:0>:ADRESL<7:6>).
        let (adresh, adresl) = if adfm {
            (
                ((self.an0_sample >> 8) & 0x03) as u8,
                (self.an0_sample & 0xFF) as u8,
            )
        } else {
            let shifted = self.an0_sample << 6;
            ((shifted >> 8) as u8, (shifted & 0xFF) as u8)
        };
        mem.write_raw(Address::from_raw(ADRESH_ADDR), adresh);
        mem.write_raw(Address::from_raw(ADRESL_ADDR), adresl);
        // GO/DONE auto-clears (DS §21.2.4).
        let con0 = mem.read_raw(Address::from_raw(ADCON0_ADDR));
        mem.write_raw(
            Address::from_raw(ADCON0_ADDR),
            con0 & !ADCON0_GODONE,
        );
        // ADIF asserts.
        let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
        mem.write_raw(Address::from_raw(PIR1_ADDR), pir1 | PIR1_ADIF);
    }

    fn handle_adcon0_write(&mut self, value: u8, _mem: &mut Memory) {
        let go_done = (value & ADCON0_GODONE) != 0;
        let adon = (value & ADCON0_ADON) != 0;
        let busy = self.pending_tcy.is_some();
        // Abort path: if firmware clears GO/DONE OR disables
        // ADON while a conversion is in flight, drop the
        // pending state.  Per DS39632E §21.6 ("Aborting a
        // Conversion"): clearing GO/DONE mid-conversion
        // aborts and does NOT update ADRESH:ADRESL.  Same
        // effect for clearing ADON (the entire ADC is
        // disabled).
        if busy && (!go_done || !adon) {
            self.pending_tcy = None;
            return;
        }
        // Trigger path: edge-sensitive on GO/DONE 0->1.  We
        // approximate the edge by gating on "not currently
        // busy", which collapses the firmware-visible
        // "while busy, writes are ignored" rule and the
        // edge-on-rise semantic into one check.  The fixed
        // 12-Tcy delay (Phase-2 simplification) lands enough
        // fidelity for the AN0-boot-threshold tests; the
        // accurate Tacq + Tconv math derived from
        // ADCON2.{ACQT, ADCS} is deferred to P2.7.
        if go_done && adon && !busy {
            self.pending_tcy = Some(12);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fresh_mem() -> Memory {
        Memory::new(Variant::Pic18F2455)
    }

    #[test]
    fn idle_tick_does_nothing() {
        let mut adc = Adc::default();
        let mut mem = fresh_mem();
        adc.tick_tcy(1000, &mut mem);
        assert!(adc.pending_tcy.is_none());
    }

    #[test]
    fn go_done_with_adon_starts_conversion() {
        let mut adc = Adc::default();
        let mut mem = fresh_mem();
        adc.on_sfr_write(ADCON0_ADDR, ADCON0_GODONE | ADCON0_ADON, &mut mem);
        assert_eq!(adc.pending_tcy, Some(12));
    }

    #[test]
    fn go_done_without_adon_does_not_trigger() {
        let mut adc = Adc::default();
        let mut mem = fresh_mem();
        adc.on_sfr_write(ADCON0_ADDR, ADCON0_GODONE, &mut mem);
        assert!(adc.pending_tcy.is_none());
    }

    #[test]
    fn conversion_completes_clears_godone_sets_adif_writes_result_adfm_right() {
        let mut adc = Adc::default();
        let mut mem = fresh_mem();
        // ADCON2.ADFM = 1 (right-justified).
        mem.write_raw(Address::from_raw(ADCON2_ADDR), ADCON2_ADFM);
        adc.set_an0_sample(0x0236); // V3.2 boot threshold.
        // Trigger.
        mem.write_raw(
            Address::from_raw(ADCON0_ADDR),
            ADCON0_GODONE | ADCON0_ADON,
        );
        adc.on_sfr_write(ADCON0_ADDR, ADCON0_GODONE | ADCON0_ADON, &mut mem);
        // Tick past the conversion window.
        adc.tick_tcy(20, &mut mem);
        // GO/DONE cleared.
        let con0 = mem.read_raw(Address::from_raw(ADCON0_ADDR));
        assert_eq!(con0 & ADCON0_GODONE, 0);
        assert_eq!(con0 & ADCON0_ADON, ADCON0_ADON, "ADON preserved");
        // ADIF asserted.
        let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
        assert_eq!(pir1 & PIR1_ADIF, PIR1_ADIF);
        // Result loaded right-justified.  0x0236 = 10 0011 0110
        // -> ADRESH = 0x02, ADRESL = 0x36.
        assert_eq!(
            mem.read_raw(Address::from_raw(ADRESH_ADDR)),
            0x02,
        );
        assert_eq!(
            mem.read_raw(Address::from_raw(ADRESL_ADDR)),
            0x36,
        );
    }

    #[test]
    fn conversion_left_justified_when_adfm_clear() {
        let mut adc = Adc::default();
        let mut mem = fresh_mem();
        // ADCON2.ADFM=0 (left-justified).
        mem.write_raw(Address::from_raw(ADCON2_ADDR), 0);
        adc.set_an0_sample(0x0236);
        adc.on_sfr_write(ADCON0_ADDR, ADCON0_GODONE | ADCON0_ADON, &mut mem);
        adc.tick_tcy(20, &mut mem);
        // 0x0236 << 6 = 0x8D80.  ADRESH = 0x8D, ADRESL = 0x80.
        assert_eq!(
            mem.read_raw(Address::from_raw(ADRESH_ADDR)),
            0x8D,
        );
        assert_eq!(
            mem.read_raw(Address::from_raw(ADRESL_ADDR)),
            0x80,
        );
    }

    #[test]
    fn an0_sample_clamps_to_10_bits() {
        let mut adc = Adc::default();
        adc.set_an0_sample(0xFFFF);
        assert_eq!(adc.an0_sample, 0x3FF);
    }

    /// Mid-conversion clear of GO/DONE aborts: pending_tcy
    /// becomes None; ADRESH/L not updated; ADIF NOT
    /// asserted.
    #[test]
    fn clearing_go_done_mid_conversion_aborts() {
        let mut adc = Adc::default();
        let mut mem = fresh_mem();
        adc.set_an0_sample(0x0236);
        // Trigger.
        adc.on_sfr_write(ADCON0_ADDR, ADCON0_GODONE | ADCON0_ADON, &mut mem);
        assert!(adc.pending_tcy.is_some());
        // Tick partway -- still in flight.
        adc.tick_tcy(5, &mut mem);
        // Firmware clears GO/DONE (still ADON=1).
        adc.on_sfr_write(ADCON0_ADDR, ADCON0_ADON, &mut mem);
        assert!(adc.pending_tcy.is_none(), "abort drops pending state");
        // Subsequent ticks are no-ops; ADIF stays low.
        adc.tick_tcy(100, &mut mem);
        let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
        assert_eq!(pir1 & PIR1_ADIF, 0);
        // ADRESH:ADRESL stay 0 (POR default; never loaded).
        assert_eq!(mem.read_raw(Address::from_raw(ADRESH_ADDR)), 0);
        assert_eq!(mem.read_raw(Address::from_raw(ADRESL_ADDR)), 0);
    }

    /// Mid-conversion clear of ADON also aborts.
    #[test]
    fn disabling_adon_mid_conversion_aborts() {
        let mut adc = Adc::default();
        let mut mem = fresh_mem();
        adc.on_sfr_write(ADCON0_ADDR, ADCON0_GODONE | ADCON0_ADON, &mut mem);
        assert!(adc.pending_tcy.is_some());
        // Firmware disables ADC (ADON=0).
        adc.on_sfr_write(ADCON0_ADDR, 0, &mut mem);
        assert!(adc.pending_tcy.is_none());
    }

    /// Re-writing GO/DONE | ADON while already busy is
    /// ignored (no restart).
    #[test]
    fn rewriting_go_done_while_busy_does_not_restart() {
        let mut adc = Adc::default();
        let mut mem = fresh_mem();
        adc.on_sfr_write(ADCON0_ADDR, ADCON0_GODONE | ADCON0_ADON, &mut mem);
        let initial = adc.pending_tcy;
        adc.tick_tcy(5, &mut mem);
        let mid = adc.pending_tcy;
        assert_ne!(initial, mid, "pending_tcy should have decremented");
        // Re-write the same bits.  pending_tcy should NOT
        // reset to 12 (no restart).
        adc.on_sfr_write(ADCON0_ADDR, ADCON0_GODONE | ADCON0_ADON, &mut mem);
        assert_eq!(adc.pending_tcy, mid, "busy re-write must not restart");
    }
}
