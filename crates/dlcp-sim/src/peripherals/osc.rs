//! Oscillator subsystem.
//!
//! The DLCP board gives both MCUs a 12 MHz external clock
//! input.  V1.71 CONTROL leaves the K20 in its primary XT
//! clock, so Fosc=12 MHz and Tcy=3 MHz.  V3.2 MAIN programs
//! the 2455 for ECPIO with PLLDIV=3 and CPUDIV=PLL/6, so the
//! PLL's fixed 96 MHz output becomes Fosc=16 MHz and Tcy=4 MHz.
//! On the simulator's 48 MHz universal clock those are 16 and
//! 12 ticks/Tcy respectively.
//!
//! This model is intentionally DLCP-scoped: it derives the
//! primary clock from CONFIG1L/CONFIG1H, tracks OSCCON.SCS and
//! IRCF writes, owns OSCCON.OSTS/IOFS and T1CON.T1RUN status
//! bits, and exposes the current ticks/Tcy to the chain
//! scheduler.  It does not synthesize fail-safe oscillator
//! interrupts or analog oscillator failures.

use crate::config::{Config, FoscMode};
use crate::memory::{Address, Memory, Variant};
use serde::{Deserialize, Serialize};

const UNIVERSAL_CLOCK_HZ: u64 = 48_000_000;
const DLCP_EXTERNAL_OSC_HZ: u32 = 12_000_000;
const PIC2455_PLL_HZ: u32 = 96_000_000;
const K20_PLL_MULTIPLIER: u32 = 4;

const OSCCON_ADDR: u16 = 0xFD3;
const OSCTUNE_ADDR: u16 = 0xF9B;
const T1CON_ADDR: u16 = 0xFCD;

const OSCCON_OSTS: u8 = 0x08;
const OSCCON_IOFS: u8 = 0x04;
const OSCCON_SCS_MASK: u8 = 0x03;
const T1CON_T1RUN: u8 = 0x40;
const T1CON_T1OSCEN: u8 = 0x08;
const OSCTUNE_INTSRC: u8 = 0x80;

/// Deterministic clock-switch interval.  DS39632E Figures 3-2
/// and 3-4 say clock transition typically occurs within 2-4
/// TOSC; the Rust model rounds that to four instruction-cycle
/// ticks so tests can observe the pending state without trying
/// to model sub-Tcy Q-cycle edges.
pub const OSC_SWITCH_DELAY_TCY: u32 = 4;

/// Deterministic HFINTOSC ready interval used for IOFS.  The
/// datasheets define a TIOBST settling interval; the DLCP
/// firmware only polls the status bit, so this model uses one
/// bounded simulator delay and exposes it as a test constant.
pub const HFINTOSC_READY_DELAY_TCY: u32 = 1024;

/// Deterministic PLL-ready delay.  Datasheets specify an
/// approximate 2 ms lock interval for PLL modes; the simulator
/// keeps that as a named policy point while DLCP's production
/// configs start from an already-ready primary clock.
pub const PLL_READY_DELAY_TCY: u32 = 8_000;

#[derive(Serialize, Deserialize, Clone, Copy, Debug, Eq, PartialEq)]
pub enum ClockSource {
    Primary,
    Secondary,
    Internal,
}

#[derive(Serialize, Deserialize, Clone, Copy, Debug)]
struct PendingSwitch {
    source: ClockSource,
    ticks_per_tcy: u32,
    delay_remaining_tcy: u32,
    set_iofs: bool,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct Osc {
    variant: Variant,
    primary_ticks_per_tcy: u32,
    current_ticks_per_tcy: u32,
    source: ClockSource,
    pending_switch: Option<PendingSwitch>,
}

impl Osc {
    pub fn new(variant: Variant) -> Self {
        let factor = ticks_per_tcy(variant);
        Osc {
            variant,
            primary_ticks_per_tcy: factor,
            current_ticks_per_tcy: factor,
            source: ClockSource::Primary,
            pending_switch: None,
        }
    }

    pub fn configure_from_config(&mut self, config: &Config) {
        self.primary_ticks_per_tcy = primary_ticks_per_tcy(self.variant, config);
        if self.source == ClockSource::Primary && self.pending_switch.is_none() {
            self.current_ticks_per_tcy = self.primary_ticks_per_tcy;
        }
    }

    pub fn reset_state(&mut self) {
        self.source = ClockSource::Primary;
        self.current_ticks_per_tcy = self.primary_ticks_per_tcy;
        self.pending_switch = None;
    }

    pub const fn current_source(&self) -> ClockSource {
        self.source
    }

    pub const fn ticks_per_tcy(&self) -> u32 {
        self.current_ticks_per_tcy
    }

    pub fn on_sfr_write(&mut self, addr: u16, _value: u8, mem: &mut Memory) {
        match addr {
            OSCCON_ADDR | OSCTUNE_ADDR | T1CON_ADDR => {
                self.begin_switch(requested_source(mem), mem);
            }
            _ => {}
        }
    }

    pub fn tick_tcy(&mut self, n: u32, mem: &mut Memory) {
        let Some(mut pending) = self.pending_switch else {
            return;
        };
        if n < pending.delay_remaining_tcy {
            pending.delay_remaining_tcy -= n;
            self.pending_switch = Some(pending);
            return;
        }
        self.pending_switch = None;
        self.complete_switch(pending, mem);
    }

    fn begin_switch(&mut self, source: ClockSource, mem: &mut Memory) {
        let ticks_per_tcy = match source {
            ClockSource::Primary => self.primary_ticks_per_tcy,
            ClockSource::Secondary => secondary_ticks_per_tcy(),
            ClockSource::Internal => internal_ticks_per_tcy(self.variant, mem),
        };
        let set_iofs = match source {
            ClockSource::Internal => internal_hf_enabled(mem),
            ClockSource::Primary => false,
            ClockSource::Secondary => false,
        };
        clear_clock_status(mem);
        self.pending_switch = Some(PendingSwitch {
            source,
            ticks_per_tcy,
            delay_remaining_tcy: if source == ClockSource::Internal && set_iofs {
                HFINTOSC_READY_DELAY_TCY
            } else {
                OSC_SWITCH_DELAY_TCY
            },
            set_iofs,
        });
    }

    fn complete_switch(&mut self, pending: PendingSwitch, mem: &mut Memory) {
        self.source = pending.source;
        self.current_ticks_per_tcy = pending.ticks_per_tcy;
        match pending.source {
            ClockSource::Primary => {
                write_osccon_status(mem, true, false);
                write_t1run(mem, false);
            }
            ClockSource::Secondary => {
                write_osccon_status(mem, false, false);
                write_t1run(mem, true);
            }
            ClockSource::Internal => {
                write_osccon_status(mem, false, pending.set_iofs);
                write_t1run(mem, false);
            }
        }
    }
}

/// Universal-clock conversion factor for the default DLCP
/// clocking of each variant.  Returns the number of 48 MHz
/// universal clock ticks per instruction cycle (Tcy).
pub const fn ticks_per_tcy(variant: Variant) -> u32 {
    match variant {
        Variant::Pic18F25K20 => 16,
        Variant::Pic18F2455 => 12,
    }
}

fn ticks_per_tcy_from_fosc_hz(fosc_hz: u32) -> u32 {
    let fosc = fosc_hz.max(1) as u64;
    (((UNIVERSAL_CLOCK_HZ * 4) + (fosc / 2)) / fosc)
        .try_into()
        .expect("ticks/Tcy fits u32")
}

fn primary_ticks_per_tcy(variant: Variant, config: &Config) -> u32 {
    let fosc_hz = match variant {
        Variant::Pic18F25K20 => primary_fosc_hz_k20(config),
        Variant::Pic18F2455 => primary_fosc_hz_2455(config),
    };
    ticks_per_tcy_from_fosc_hz(fosc_hz)
}

fn primary_fosc_hz_k20(config: &Config) -> u32 {
    match config.fosc() {
        FoscMode::INTIO | FoscMode::INTCKO | FoscMode::INTXT | FoscMode::INTHS => 1_000_000,
        FoscMode::XTPLL | FoscMode::ECPLL | FoscMode::ECPIO | FoscMode::HSPLL => {
            DLCP_EXTERNAL_OSC_HZ * K20_PLL_MULTIPLIER
        }
        _ => DLCP_EXTERNAL_OSC_HZ,
    }
}

fn primary_fosc_hz_2455(config: &Config) -> u32 {
    match config.fosc() {
        FoscMode::XTPLL | FoscMode::ECPLL | FoscMode::ECPIO | FoscMode::HSPLL => {
            PIC2455_PLL_HZ / pic2455_cpudiv_pll(config.cpudiv())
        }
        FoscMode::INTIO | FoscMode::INTCKO | FoscMode::INTXT | FoscMode::INTHS => 1_000_000,
        _ => DLCP_EXTERNAL_OSC_HZ / pic2455_cpudiv_non_pll(config.cpudiv()),
    }
}

const fn pic2455_cpudiv_pll(bits: u8) -> u32 {
    match bits & 0b11 {
        0b00 => 2,
        0b01 => 3,
        0b10 => 4,
        0b11 => 6,
        _ => unreachable!(),
    }
}

const fn pic2455_cpudiv_non_pll(bits: u8) -> u32 {
    match bits & 0b11 {
        0b00 => 1,
        0b01 => 2,
        0b10 => 3,
        0b11 => 4,
        _ => unreachable!(),
    }
}

fn internal_ticks_per_tcy(variant: Variant, mem: &Memory) -> u32 {
    ticks_per_tcy_from_fosc_hz(internal_fosc_hz(variant, mem))
}

fn internal_fosc_hz(variant: Variant, mem: &Memory) -> u32 {
    let osccon = mem.read_raw(Address::from_raw(OSCCON_ADDR));
    let osctune = mem.read_raw(Address::from_raw(OSCTUNE_ADDR));
    let ircf = (osccon >> 4) & 0b111;
    let low_from_hf = (osctune & OSCTUNE_INTSRC) != 0;
    match variant {
        Variant::Pic18F25K20 => match ircf {
            0b111 => 16_000_000,
            0b110 => 8_000_000,
            0b101 => 4_000_000,
            0b100 => 2_000_000,
            0b011 => 1_000_000,
            0b010 => 500_000,
            0b001 => 250_000,
            _ if low_from_hf => 31_250,
            _ => 31_000,
        },
        Variant::Pic18F2455 => match ircf {
            0b111 => 8_000_000,
            0b110 => 4_000_000,
            0b101 => 2_000_000,
            0b100 => 1_000_000,
            0b011 => 500_000,
            0b010 => 250_000,
            0b001 => 125_000,
            _ if low_from_hf => 31_250,
            _ => 31_000,
        },
    }
}

fn requested_source(mem: &Memory) -> ClockSource {
    let osccon = mem.read_raw(Address::from_raw(OSCCON_ADDR));
    match osccon & OSCCON_SCS_MASK {
        0b00 => ClockSource::Primary,
        0b01 => {
            let t1con = mem.read_raw(Address::from_raw(T1CON_ADDR));
            if (t1con & T1CON_T1OSCEN) != 0 {
                ClockSource::Secondary
            } else {
                ClockSource::Primary
            }
        }
        _ => ClockSource::Internal,
    }
}

fn internal_hf_enabled(mem: &Memory) -> bool {
    let osccon = mem.read_raw(Address::from_raw(OSCCON_ADDR));
    let osctune = mem.read_raw(Address::from_raw(OSCTUNE_ADDR));
    ((osccon >> 4) & 0b111) != 0 || (osctune & OSCTUNE_INTSRC) != 0
}

fn secondary_ticks_per_tcy() -> u32 {
    ticks_per_tcy_from_fosc_hz(32_768)
}

fn clear_clock_status(mem: &mut Memory) {
    write_osccon_status(mem, false, false);
    write_t1run(mem, false);
}

fn write_osccon_status(mem: &mut Memory, osts: bool, iofs: bool) {
    let mut osccon = mem.read_raw(Address::from_raw(OSCCON_ADDR));
    osccon &= !(OSCCON_OSTS | OSCCON_IOFS);
    if osts {
        osccon |= OSCCON_OSTS;
    }
    if iofs {
        osccon |= OSCCON_IOFS;
    }
    mem.write_raw(Address::from_raw(OSCCON_ADDR), osccon);
}

fn write_t1run(mem: &mut Memory, t1run: bool) {
    let mut t1con = mem.read_raw(Address::from_raw(T1CON_ADDR));
    if t1run {
        t1con |= T1CON_T1RUN;
    } else {
        t1con &= !T1CON_T1RUN;
    }
    mem.write_raw(Address::from_raw(T1CON_ADDR), t1con);
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
