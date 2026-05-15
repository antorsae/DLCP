//! Pin network — cross-core electrical coupling.
//!
//! ## Phase-3.2 scope
//!
//! Three coupling primitives the spec calls out:
//!
//!   * `couple_uart(src_core, src_tx_pin, dst_core,
//!     dst_rx_pin)` — wires source-core EUSART TX to
//!     destination-core EUSART RX.  Bytes that complete
//!     shifting on the source's TSR appear in the
//!     destination's RCREG after the configured
//!     propagation delay.
//!   * `couple_pin(src_core, src_pin, dst_core, dst_pin)` —
//!     general-purpose pin-to-pin wire (e.g. for the
//!     MCLR-to-RA0 wakeup line, button-matrix rows,
//!     LCD strobes).  When the source-core LATx bit
//!     changes, the destination-core PORTx bit
//!     mirrors after the propagation delay.
//!   * `couple_i2c_slave(master_core, master_sda,
//!     master_scl, slave)` — wires the MAIN's MSSP to a
//!     virtual I²C slave (TAS3108 model in V3.2).
//!
//! ## Phase-3.2 minimum-viable
//!
//! P3.2 lands the API surface only -- couple methods
//! record the wiring in a `PinNet` struct, but the actual
//! event-driven byte/edge propagation is wired up in
//! P3.5 (multicore parity).  The Phase-3.2 verification
//! gate just exercises construction + the public method
//! signatures; behavioural parity comes via the chain
//! parity tests in P3.5+.

use crate::peripherals::eusart;
use serde::{Deserialize, Serialize};

/// One UART coupling.  Source TSR -> destination RCREG
/// via the chain's event queue.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, Eq)]
pub struct UartCoupling {
    pub src_core: usize,
    pub src_tx_pin: PinId,
    pub dst_core: usize,
    pub dst_rx_pin: PinId,
}

/// One general-purpose pin-to-pin coupling.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, Eq)]
pub struct PinCoupling {
    pub src_core: usize,
    pub src_pin: PinId,
    pub dst_core: usize,
    pub dst_pin: PinId,
}

/// One I²C master/slave coupling.  Phase-3.2 stores the
/// slave by an opaque ID; P3.5 dispatches to a slave
/// trait implementation.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, Eq)]
pub struct I2cCoupling {
    pub master_core: usize,
    pub master_sda: PinId,
    pub master_scl: PinId,
    pub slave_id: u32,
}

/// Pin identifier (port-letter + bit).  Phase-3.2 uses a
/// flat enum; future expansion (peripheral-output muxes,
/// open-drain etc.) can grow attributes here.
#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct PinId {
    pub port: PortLetter,
    pub bit: u8,
}

#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum PortLetter {
    A,
    B,
    C,
    D,
    E,
}

/// Network of cross-core couplings owned by the chain.
#[derive(Serialize, Deserialize, Clone, Debug, Default)]
pub struct PinNet {
    pub uart: Vec<UartCoupling>,
    pub pin: Vec<PinCoupling>,
    pub i2c: Vec<I2cCoupling>,
}

impl PinNet {
    pub fn new() -> Self {
        PinNet::default()
    }

    pub fn couple_uart(
        &mut self,
        src_core: usize,
        src_tx_pin: PinId,
        dst_core: usize,
        dst_rx_pin: PinId,
    ) {
        // Reject self-loops outright: real silicon cannot route a
        // core's TX into its own RX (the TX and RX shift registers
        // share no internal path), and the firmware-driven
        // no-echo invariant in `chain.rs::tests::three_core_silicon_ring_uart_topology_has_no_echo_or_duplicates`
        // is a structural cardinality check downstream of this
        // coupling.  Catching the misconfiguration here surfaces
        // the topology bug at fixture-build time, not as a
        // mysterious "echoed byte arrived at src" later.  Codex
        // LOW from 8e180a6 review (task #38).
        assert_ne!(
            src_core, dst_core,
            "couple_uart: src_core == dst_core ({src_core}) is a \
             self-loop, not supported by real silicon and not \
             modelled by the chain dispatcher"
        );
        self.uart.push(UartCoupling {
            src_core,
            src_tx_pin,
            dst_core,
            dst_rx_pin,
        });
    }

    pub fn couple_pin(&mut self, src_core: usize, src_pin: PinId, dst_core: usize, dst_pin: PinId) {
        self.pin.push(PinCoupling {
            src_core,
            src_pin,
            dst_core,
            dst_pin,
        });
    }

    pub fn couple_i2c_slave(
        &mut self,
        master_core: usize,
        master_sda: PinId,
        master_scl: PinId,
        slave_id: u32,
    ) {
        self.i2c.push(I2cCoupling {
            master_core,
            master_sda,
            master_scl,
            slave_id,
        });
    }
}

/// Re-export the EUSART TX-pin convention -- on PIC18 the
/// TX pin is RC6 by default; this is mostly a placeholder
/// so chain construction can write `pinnet::default_tx_pin()`
/// rather than a hard-coded magic.
pub const fn default_tx_pin() -> PinId {
    PinId {
        port: PortLetter::C,
        bit: 6,
    }
}

pub const fn default_rx_pin() -> PinId {
    PinId {
        port: PortLetter::C,
        bit: 7,
    }
}

// Pull eusart constants in just to anchor a compile-time
// "EUSART module is reachable" check; saves an `unused_import`
// warning if downstream code reorganises.
#[allow(dead_code)]
const _: u16 = eusart::TXSTA_ADDR;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_pinnet_has_no_couplings() {
        let net = PinNet::new();
        assert!(net.uart.is_empty());
        assert!(net.pin.is_empty());
        assert!(net.i2c.is_empty());
    }

    #[test]
    fn couple_uart_records_one_coupling() {
        let mut net = PinNet::new();
        net.couple_uart(0, default_tx_pin(), 1, default_rx_pin());
        assert_eq!(net.uart.len(), 1);
        let coupling = &net.uart[0];
        assert_eq!(coupling.src_core, 0);
        assert_eq!(coupling.dst_core, 1);
    }

    #[test]
    fn couple_pin_records_one_coupling() {
        let mut net = PinNet::new();
        let src = PinId {
            port: PortLetter::C,
            bit: 0,
        };
        let dst = PinId {
            port: PortLetter::A,
            bit: 0,
        };
        net.couple_pin(0, src, 1, dst);
        assert_eq!(net.pin.len(), 1);
        assert_eq!(net.pin[0].src_pin, src);
        assert_eq!(net.pin[0].dst_pin, dst);
    }

    #[test]
    fn couple_i2c_slave_records_one_coupling() {
        let mut net = PinNet::new();
        let sda = PinId {
            port: PortLetter::C,
            bit: 4,
        };
        let scl = PinId {
            port: PortLetter::C,
            bit: 3,
        };
        net.couple_i2c_slave(0, sda, scl, 42);
        assert_eq!(net.i2c.len(), 1);
        assert_eq!(net.i2c[0].slave_id, 42);
    }

    #[test]
    fn default_pin_constants_match_pic18_eusart_assignment() {
        assert_eq!(
            default_tx_pin(),
            PinId {
                port: PortLetter::C,
                bit: 6
            }
        );
        assert_eq!(
            default_rx_pin(),
            PinId {
                port: PortLetter::C,
                bit: 7
            }
        );
    }
}
