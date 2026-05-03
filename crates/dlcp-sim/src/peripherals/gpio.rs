//! GPIO PORT/TRIS/LAT side effects.
//!
//! FID-14 scope is deliberately small: enough silicon semantics for
//! firmware-visible pin reads and chain pin coupling without pretending to
//! model board-level analog voltages.  The model keeps PORTx as the sampled
//! pin level, LATx as the output latch, and TRISx as the direction gate.
//! Writes to LATx or TRISx immediately refresh PORTx output bits; input bits
//! retain the externally injected PORTx level.

use crate::memory::{Address, Memory, Variant};
use crate::pinnet::PortLetter;

pub const PORTA_ADDR: u16 = 0xF80;
pub const PORTB_ADDR: u16 = 0xF81;
pub const PORTC_ADDR: u16 = 0xF82;
pub const PORTD_ADDR: u16 = 0xF83;
pub const PORTE_ADDR: u16 = 0xF84;

pub const LATA_ADDR: u16 = 0xF89;
pub const LATB_ADDR: u16 = 0xF8A;
pub const LATC_ADDR: u16 = 0xF8B;
pub const LATD_ADDR: u16 = 0xF8C;
pub const LATE_ADDR: u16 = 0xF8D;

pub const TRISA_ADDR: u16 = 0xF92;
pub const TRISB_ADDR: u16 = 0xF93;
pub const TRISC_ADDR: u16 = 0xF94;
pub const TRISD_ADDR: u16 = 0xF95;
pub const TRISE_ADDR: u16 = 0xF96;

pub const ANSEL_ADDR: u16 = 0xF7E;
pub const ANSELH_ADDR: u16 = 0xF7F;
pub const UCON_ADDR: u16 = 0xF6D;

pub const INTCON3_ADDR: u16 = 0xFF0;
pub const INTCON2_ADDR: u16 = 0xFF1;
pub const INTCON_ADDR: u16 = 0xFF2;

const UCON_USBEN: u8 = 1 << 3;
const INTCON_RBIF: u8 = 1 << 0;
const INTCON_INT0IF: u8 = 1 << 1;
const INTCON3_INT1IF: u8 = 1 << 0;
const INTCON3_INT2IF: u8 = 1 << 1;

#[derive(Clone, Debug)]
pub struct Gpio {
    variant: Variant,
    external_port: [u8; 5],
}

impl Gpio {
    pub fn new(variant: Variant) -> Self {
        Gpio {
            variant,
            external_port: [0; 5],
        }
    }

    pub fn reset_state(&mut self) {
        // No hidden GPIO state today; PORTx itself stores injected pin levels.
    }

    pub fn on_sfr_write(&mut self, addr: u16, value: u8, mem: &mut Memory) {
        if let Some(port) = port_from_port_addr(addr) {
            // PIC18 writes to PORTx update the output latch.  The executor has
            // already written PORTx; mirror the firmware-intended byte to LATx
            // before recomputing the sampled pin state.
            mem.write_raw(Address::from_raw(lat_addr(port)), value);
            self.refresh_port(port, mem);
            return;
        }
        if let Some(port) = port_from_lat_addr(addr).or_else(|| port_from_tris_addr(addr)) {
            self.refresh_port(port, mem);
            return;
        }
        match addr {
            ANSEL_ADDR | ANSELH_ADDR => {
                if self.variant == Variant::Pic18F25K20 {
                    self.refresh_port(PortLetter::A, mem);
                    self.refresh_port(PortLetter::B, mem);
                }
            }
            UCON_ADDR => {
                if self.variant == Variant::Pic18F2455 {
                    self.refresh_port(PortLetter::C, mem);
                }
            }
            _ => {}
        }
    }

    pub fn sync_from_memory(&mut self, mem: &mut Memory) {
        self.refresh_port(PortLetter::A, mem);
        self.refresh_port(PortLetter::B, mem);
        self.refresh_port(PortLetter::C, mem);
        self.refresh_port(PortLetter::D, mem);
        self.refresh_port(PortLetter::E, mem);
    }

    /// Inject an external level onto an input pin.  Returns true when the
    /// firmware-visible digital PORT bit changed.
    pub fn drive_external_pin(
        &mut self,
        port: PortLetter,
        bit: u8,
        high: bool,
        mem: &mut Memory,
    ) -> bool {
        assert!(bit < 8, "GPIO bit must be 0..=7, got {bit}");
        if !self.is_general_input_pin(port, bit, mem) {
            self.refresh_port(port, mem);
            return false;
        }
        let old_level = read_pin_level(mem, port, bit);
        let slot = &mut self.external_port[port_index(port)];
        if high {
            *slot |= 1 << bit;
        } else {
            *slot &= !(1 << bit);
        }
        self.refresh_port(port, mem);
        let new_level = read_pin_level(mem, port, bit);
        if old_level != new_level {
            self.update_edge_flags(port, bit, old_level, new_level, mem);
            true
        } else {
            false
        }
    }

    fn refresh_port(&self, port: PortLetter, mem: &mut Memory) {
        let port_addr = port_addr(port);
        let tris = mem.read_raw(Address::from_raw(tris_addr(port)));
        let lat = mem.read_raw(Address::from_raw(lat_addr(port)));
        let current_port = mem.read_raw(Address::from_raw(port_addr));
        let external = self.external_port[port_index(port)];
        let input_mask = tris;
        let output_mask = !tris;
        let mut live = (external & input_mask) | (lat & output_mask);

        live &= !self.analog_digital_off_mask(port, mem);

        if self.variant == Variant::Pic18F2455 && port == PortLetter::C {
            let ucon = mem.read_raw(Address::from_raw(UCON_ADDR));
            if ucon & UCON_USBEN != 0 {
                // RC4/RC5 are D-/D+ while USB is enabled.  Treat them as
                // peripheral-owned pins, not GPIO outputs driven from LATC.
                live = (live & !0x30) | (current_port & 0x30);
            }
        }

        mem.write_raw(Address::from_raw(port_addr), live);
    }

    fn analog_digital_off_mask(&self, port: PortLetter, mem: &Memory) -> u8 {
        if self.variant != Variant::Pic18F25K20 {
            return 0;
        }
        match port {
            PortLetter::A => mem.read_raw(Address::from_raw(ANSEL_ADDR)) & 0x3F,
            PortLetter::B => {
                let anselh = mem.read_raw(Address::from_raw(ANSELH_ADDR));
                ((anselh & 0x07) << 0) | ((anselh & 0x18) << 1)
            }
            _ => 0,
        }
    }

    fn is_general_input_pin(&self, port: PortLetter, bit: u8, mem: &Memory) -> bool {
        let tris = mem.read_raw(Address::from_raw(tris_addr(port)));
        if tris & (1 << bit) == 0 {
            return false;
        }
        if self.variant == Variant::Pic18F2455 && port == PortLetter::C && (bit == 4 || bit == 5) {
            let ucon = mem.read_raw(Address::from_raw(UCON_ADDR));
            return ucon & UCON_USBEN == 0;
        }
        true
    }

    fn update_edge_flags(
        &self,
        port: PortLetter,
        bit: u8,
        old_high: bool,
        new_high: bool,
        mem: &mut Memory,
    ) {
        if port != PortLetter::B {
            return;
        }
        let rising = !old_high && new_high;
        let falling = old_high && !new_high;
        let intcon2 = mem.read_raw(Address::from_raw(INTCON2_ADDR));
        match bit {
            0 => {
                let wants_rising = intcon2 & (1 << 6) != 0;
                if (wants_rising && rising) || (!wants_rising && falling) {
                    set_bit(mem, INTCON_ADDR, INTCON_INT0IF);
                }
            }
            1 => {
                let wants_rising = intcon2 & (1 << 5) != 0;
                if (wants_rising && rising) || (!wants_rising && falling) {
                    set_bit(mem, INTCON3_ADDR, INTCON3_INT1IF);
                }
            }
            2 => {
                let wants_rising = intcon2 & (1 << 4) != 0;
                if (wants_rising && rising) || (!wants_rising && falling) {
                    set_bit(mem, INTCON3_ADDR, INTCON3_INT2IF);
                }
            }
            4..=7 => {
                set_bit(mem, INTCON_ADDR, INTCON_RBIF);
            }
            _ => {}
        }
    }
}

const fn port_index(port: PortLetter) -> usize {
    match port {
        PortLetter::A => 0,
        PortLetter::B => 1,
        PortLetter::C => 2,
        PortLetter::D => 3,
        PortLetter::E => 4,
    }
}

pub fn read_pin_level(mem: &Memory, port: PortLetter, bit: u8) -> bool {
    assert!(bit < 8, "GPIO bit must be 0..=7, got {bit}");
    mem.read_raw(Address::from_raw(port_addr(port))) & (1 << bit) != 0
}

pub const fn port_addr(port: PortLetter) -> u16 {
    match port {
        PortLetter::A => PORTA_ADDR,
        PortLetter::B => PORTB_ADDR,
        PortLetter::C => PORTC_ADDR,
        PortLetter::D => PORTD_ADDR,
        PortLetter::E => PORTE_ADDR,
    }
}

pub const fn lat_addr(port: PortLetter) -> u16 {
    match port {
        PortLetter::A => LATA_ADDR,
        PortLetter::B => LATB_ADDR,
        PortLetter::C => LATC_ADDR,
        PortLetter::D => LATD_ADDR,
        PortLetter::E => LATE_ADDR,
    }
}

pub const fn tris_addr(port: PortLetter) -> u16 {
    match port {
        PortLetter::A => TRISA_ADDR,
        PortLetter::B => TRISB_ADDR,
        PortLetter::C => TRISC_ADDR,
        PortLetter::D => TRISD_ADDR,
        PortLetter::E => TRISE_ADDR,
    }
}

fn port_from_port_addr(addr: u16) -> Option<PortLetter> {
    match addr {
        PORTA_ADDR => Some(PortLetter::A),
        PORTB_ADDR => Some(PortLetter::B),
        PORTC_ADDR => Some(PortLetter::C),
        PORTD_ADDR => Some(PortLetter::D),
        PORTE_ADDR => Some(PortLetter::E),
        _ => None,
    }
}

fn port_from_lat_addr(addr: u16) -> Option<PortLetter> {
    match addr {
        LATA_ADDR => Some(PortLetter::A),
        LATB_ADDR => Some(PortLetter::B),
        LATC_ADDR => Some(PortLetter::C),
        LATD_ADDR => Some(PortLetter::D),
        LATE_ADDR => Some(PortLetter::E),
        _ => None,
    }
}

fn port_from_tris_addr(addr: u16) -> Option<PortLetter> {
    match addr {
        TRISA_ADDR => Some(PortLetter::A),
        TRISB_ADDR => Some(PortLetter::B),
        TRISC_ADDR => Some(PortLetter::C),
        TRISD_ADDR => Some(PortLetter::D),
        TRISE_ADDR => Some(PortLetter::E),
        _ => None,
    }
}

fn set_bit(mem: &mut Memory, addr: u16, bit: u8) {
    let value = mem.read_raw(Address::from_raw(addr)) | bit;
    mem.write_raw(Address::from_raw(addr), value);
}
