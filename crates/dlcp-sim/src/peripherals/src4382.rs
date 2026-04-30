//! TI SRC4382 combo Sample-Rate Converter / Digital Audio
//! Interface Receiver-Transmitter I²C slave model.
//!
//! Identified as the DLCP's "secondary I²C device" (called
//! `cfg71` in gpsim, after its 7-bit address `0x71`).  The
//! identification was made by codex-cli analysing the
//! firmware's I²C wire protocol:
//!
//! * Wire write protocol: `START | 0xE2 | subaddr | data | STOP`
//!   (V3.2 firmware `i2c_secondary_dev_write` at
//!   `src/dlcp_fw/asm/dlcp_main_v32.asm:8179`).
//! * SRC4382 datasheet I²C address byte: `11100 A1 A0 R/W`;
//!   with A1=0, A0=1 (DLCP strapping): write `0xE2`, read `0xE3`.
//!   Confirmed match.
//! * Register-map fingerprint: page-0 controls at `0x01..0x33`,
//!   `0x00` reserved -- matches firmware's sparse `0x01..0x2E`
//!   access pattern.  Specific decode:
//!     - `0x08` = BYPMUX (bypass output mux) -- gated cmd
//!       dispatch pair (`asm:1418-1429`).
//!     - `0x0D` = RXMUX (RX1-RX4 selection) -- "amp routing".
//!     - `0x12 / 0x13` = non-PCM detection / receiver status
//!       -- read by firmware via `i2c_secondary_dev_random_read`.
//!     - `0x1B / 0x1C / 0x1D` = GPO1/GPO2/GPO3 control.  These
//!       are how `hw_standby_shutdown`'s "rail control" works:
//!       the SRC's GPO pins drive external amp-standby
//!       circuits, NOT an internal PMIC.
//!     - `0x2D / 0x2E` = SRC control.
//! * Hardware: 48-pin TQFP marked `SRC4382I` near the digital-
//!   input section (AES/S-PDIF), confirmed by external
//!   diyAudio chip-list reference.
//!
//! ## Phase-4 scope
//!
//! Models enough state to:
//!
//! * ACK the V3.2 firmware's address phase (`0xE2` / `0xE3`)
//!   so `i2c_secondary_dev_write` and
//!   `i2c_secondary_dev_random_read` complete cleanly without
//!   tripping the V3.2 `diag_i` I²C-fault counter via the
//!   `i2c_byte_tx` ACKSTAT-after-write hook.  Without this
//!   slave, every secondary-device write NACKs the address
//!   phase and saturates `diag_i` to `0x0F` during idle on a
//!   MAIN-only chain (documented backend divergence in
//!   `test_v32_diag_counters_stay_zero_during_extended_idle`).
//!
//! * Latch register writes into a 256-byte file with
//!   subaddress auto-increment, so subsequent reads return the
//!   firmware's most-recently-written value.  Sufficient for
//!   the layer5_diag_counters test family which only needs the
//!   ACKSTAT-clean baseline; tests that depend on real SRC4382
//!   audio behaviour (sample-rate detection, lock indicator)
//!   are out of scope here.
//!
//! ## What this file does NOT cover
//!
//! * Real SRC4382 audio function -- coefficients are stored
//!   but no SRC math runs.
//! * Status registers `0x12 / 0x13` (non-PCM detection /
//!   receiver status) read back whatever the firmware last
//!   wrote (or 0).  A future `set_status(...)` knob can
//!   override defaults to simulate "lock detected" / "input
//!   present" if a test needs to drive that path.  For now,
//!   the firmware's polls just see the latched / zero value.
//! * The `0xC0..0xFF` page-1 (extended) register space is
//!   present in the silicon but the V3.2 firmware doesn't
//!   appear to access it.  Modeled as the same 256-byte file
//!   for simplicity; if a future test needs page-paging, this
//!   model can be split.
//! * Fault-injection knobs (address-NACK counter, SCL stretch,
//!   etc.) are not implemented here.  The TAS3108 model has
//!   them; if a future SRC4382 robustness test needs them, copy
//!   the pattern from `tas3108.rs::set_address_nack_count`.

#![allow(dead_code, reason = "Phase-4 scaffold; extended use lands in follow-up commits")]

/// Number of subaddresses the slave's register file covers.
/// 8-bit subaddress space -- 256 entries.
const SUBADDR_COUNT: usize = 256;

/// SRC4382 strapping pins (A1, A0).  In the DLCP, A1=0 and
/// A0=1 are pulled by the schematic, giving the I²C address
/// byte format `11100 0 1 R/W` -> write `0xE2`, read `0xE3`.
/// Other strappings are exposed for future flexibility but
/// the DLCP is hardcoded.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub struct StrapAddr {
    pub a1: bool,
    pub a0: bool,
}

impl StrapAddr {
    /// DLCP's hardcoded strapping: A1=0, A0=1.  Write address
    /// `0xE2`, read address `0xE3`.
    pub const DLCP: Self = StrapAddr { a1: false, a0: true };

    /// Compute the slave write-address byte (R/W = 0).
    pub const fn write_address(self) -> u8 {
        let mut byte = 0b1110_0000_u8;
        if self.a1 {
            byte |= 1 << 2;
        }
        if self.a0 {
            byte |= 1 << 1;
        }
        byte
    }
}

/// I²C transaction phase.  Same shape as Tas3108's Phase --
/// I²C protocol semantics are device-agnostic at the byte
/// level.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
enum Phase {
    /// No transaction in progress.  The next byte from the
    /// master is interpreted as the slave-address byte.
    Idle,
    /// Address byte didn't match this slave; the slave is
    /// "off the bus" for the current transaction and drops
    /// every subsequent byte.  Cleared by `on_start` /
    /// `on_stop` / `on_repeated_start`.
    Ignored,
    /// Address matched with R/W = write.  The next byte is
    /// the subaddress.
    AwaitingSubaddress,
    /// Inside a write transaction; subaddress already latched.
    /// Subsequent bytes are data; subaddress auto-increments.
    Writing { next_subaddr: u8 },
    /// Address matched with R/W = read.  The slave provides
    /// bytes via `provide_rx_byte` starting at the latched
    /// subaddress.
    Reading { next_subaddr: u8 },
}

impl Default for Phase {
    fn default() -> Self {
        Phase::Idle
    }
}

/// SRC4382 I²C slave model.
#[derive(Clone, Debug)]
pub struct Src4382 {
    /// Hardware strap state.  Determines the slave-address
    /// byte the master must use (`write_address()` /
    /// `write_address() | 1`).  DLCP is hardcoded to
    /// `StrapAddr::DLCP`; the constructor exposes the strap
    /// for future board variants.
    strap: StrapAddr,
    /// 256-byte register file indexed by subaddress.  Reads
    /// of unwritten subaddresses return 0.
    regs: Box<[u8; SUBADDR_COUNT]>,
    /// Most-recently-latched subaddress (post-
    /// `AwaitingSubaddress`).  Persists across STOPs so a
    /// write followed by a repeated-start read can reuse it.
    /// `None` until the master issues a write transaction
    /// with a subaddress -- a read attempt before any latch
    /// gets NACKed.
    last_latched_subaddr: Option<u8>,
    /// Current transaction state.
    phase: Phase,
    /// Diagnostic counters (matches Tas3108 surface).
    pub bytes_acked: u64,
    pub bytes_nacked: u64,
}

impl Default for Src4382 {
    fn default() -> Self {
        Self::new(StrapAddr::DLCP)
    }
}

impl Src4382 {
    /// Construct a fresh SRC4382 slave with the given hardware
    /// strap.  All registers are zero-initialised; no
    /// transaction is in progress.
    pub fn new(strap: StrapAddr) -> Self {
        Src4382 {
            strap,
            regs: Box::new([0u8; SUBADDR_COUNT]),
            last_latched_subaddr: None,
            phase: Phase::Idle,
            bytes_acked: 0,
            bytes_nacked: 0,
        }
    }

    /// Slave-address byte the master must use to ADDRESS this
    /// device for a write transaction.  Read-address is
    /// `write_address() | 1`.  For `StrapAddr::DLCP` returns
    /// `0xE2`; read returns `0xE3`.
    pub fn write_address(&self) -> u8 {
        self.strap.write_address()
    }

    /// Read the byte currently stored at `subaddr`.  Returns
    /// 0 for unwritten subaddresses.  Useful for asserting
    /// that a firmware-side I²C write actually committed.
    pub fn read_subaddr(&self, subaddr: u8) -> u8 {
        self.regs[subaddr as usize]
    }

    /// Direct register write (test helper, bypasses the I²C
    /// state machine).  Used by tests that want to seed
    /// receiver-status / non-PCM-detection registers (`0x12`,
    /// `0x13`) with simulated input-state values before
    /// running firmware that polls them.
    pub fn poke_subaddr(&mut self, subaddr: u8, value: u8) {
        self.regs[subaddr as usize] = value;
    }

    /// Reset transaction state on a master-issued START.
    pub fn on_start(&mut self) {
        self.phase = Phase::Idle;
    }

    /// Reset transaction state on a master-issued STOP.
    pub fn on_stop(&mut self) {
        self.phase = Phase::Idle;
    }

    /// Master-issued Repeated-Start.  Same as `on_start` --
    /// the latched subaddress is preserved (see
    /// `last_latched_subaddr`) so a write-then-repeated-start
    /// read works.
    pub fn on_repeated_start(&mut self) {
        self.phase = Phase::Idle;
    }

    /// Consume a master-driven TX byte.  Returns `true` if
    /// the slave ACKs, `false` for NACK.
    pub fn consume_tx_byte(&mut self, byte: u8) -> bool {
        let acked = match self.phase {
            Phase::Idle => self.handle_address_byte(byte),
            Phase::Ignored => false,
            Phase::AwaitingSubaddress => self.handle_subaddress_byte(byte),
            Phase::Writing { next_subaddr } => self.handle_write_data_byte(byte, next_subaddr),
            Phase::Reading { .. } => false,
        };
        if acked {
            self.bytes_acked += 1;
        } else {
            self.bytes_nacked += 1;
        }
        acked
    }

    fn handle_address_byte(&mut self, byte: u8) -> bool {
        let write_addr = self.write_address();
        let read_addr = write_addr | 1;
        // SRC4382 does NOT have a broadcast-ACK quirk (unlike
        // the TAS3108).  Only its own write/read addresses
        // are recognised; everything else NACKs and
        // transitions to Ignored for the rest of the
        // transaction.
        if byte == write_addr {
            self.phase = Phase::AwaitingSubaddress;
            true
        } else if byte == read_addr {
            match self.last_latched_subaddr {
                Some(start) => {
                    self.phase = Phase::Reading { next_subaddr: start };
                    true
                }
                None => {
                    // Read before any subaddress was latched:
                    // NACK and go Ignored (same strict-misuse
                    // shape as the TAS3108 model).
                    self.phase = Phase::Ignored;
                    false
                }
            }
        } else {
            self.phase = Phase::Ignored;
            false
        }
    }

    fn handle_subaddress_byte(&mut self, byte: u8) -> bool {
        self.last_latched_subaddr = Some(byte);
        self.phase = Phase::Writing { next_subaddr: byte };
        true
    }

    fn handle_write_data_byte(&mut self, byte: u8, next_subaddr: u8) -> bool {
        self.regs[next_subaddr as usize] = byte;
        // 8-bit subaddress wraps mod 256.
        self.phase = Phase::Writing {
            next_subaddr: next_subaddr.wrapping_add(1),
        };
        true
    }

    /// Provide one byte for a master-driven read.  Returns
    /// the register-file byte at the current subaddress and
    /// auto-increments.  Returns 0 if no read transaction is
    /// in progress.
    pub fn provide_rx_byte(&mut self) -> u8 {
        match self.phase {
            Phase::Reading { next_subaddr } => {
                let byte = self.regs[next_subaddr as usize];
                self.phase = Phase::Reading {
                    next_subaddr: next_subaddr.wrapping_add(1),
                };
                byte
            }
            _ => 0,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// DLCP strapping (`A1=0, A0=1`) gives slave address byte
    /// `0xE2` (write) / `0xE3` (read).
    #[test]
    fn dlcp_strap_address_is_e2() {
        let s = Src4382::default();
        assert_eq!(s.write_address(), 0xE2);
    }

    /// All four strapping combinations match the datasheet's
    /// `11100 A1 A0 R/W` format.
    #[test]
    fn strap_address_table_matches_datasheet() {
        let cases: [(bool, bool, u8); 4] = [
            (false, false, 0xE0),
            (false, true, 0xE2),
            (true, false, 0xE4),
            (true, true, 0xE6),
        ];
        for (a1, a0, want) in cases {
            assert_eq!(
                StrapAddr { a1, a0 }.write_address(),
                want,
                "A1={a1} A0={a0}",
            );
        }
    }

    /// `i2c_secondary_dev_write` wire sequence
    /// (`src/dlcp_fw/asm/dlcp_main_v32.asm:8179`):
    /// `START | 0xE2 | subaddr | data | STOP`.  All three
    /// payload bytes must ACK.
    #[test]
    fn secondary_dev_write_three_byte_burst_acks_all() {
        let mut s = Src4382::default();
        s.on_start();
        assert!(s.consume_tx_byte(0xE2), "address byte must ACK");
        assert!(s.consume_tx_byte(0x0D), "subaddress byte must ACK");
        assert!(s.consume_tx_byte(0x08), "data byte must ACK");
        s.on_stop();
        assert_eq!(s.bytes_acked, 3);
        assert_eq!(s.bytes_nacked, 0);
        // Data byte landed at the latched subaddress.
        assert_eq!(s.read_subaddr(0x0D), 0x08);
    }

    /// Init burst of 16 register writes from V3.2's
    /// `main_i2c_service_32f8` (asm:4807-4870).  Each
    /// transaction is independent (own START / STOP); the
    /// register file accumulates.
    #[test]
    fn init_burst_lands_all_16_registers() {
        let init = [
            (0x01u8, 0x3Fu8),
            (0x03, 0x30),
            (0x04, 0x01),
            (0x05, 0x08),
            (0x06, 0x01),
            (0x07, 0x34),
            (0x08, 0x30),
            (0x0D, 0x08),
            (0x0E, 0x08),
            (0x0F, 0x22),
            (0x10, 0x00),
            (0x11, 0x00),
            (0x1C, 0x01),
            (0x1D, 0x01),
            (0x2D, 0x02),
            (0x2E, 0x20),
        ];
        let mut s = Src4382::default();
        for &(subaddr, data) in &init {
            s.on_start();
            assert!(s.consume_tx_byte(0xE2));
            assert!(s.consume_tx_byte(subaddr));
            assert!(s.consume_tx_byte(data));
            s.on_stop();
        }
        for &(subaddr, data) in &init {
            assert_eq!(
                s.read_subaddr(subaddr),
                data,
                "subaddr 0x{:02X} should read 0x{:02X}",
                subaddr,
                data,
            );
        }
        assert_eq!(s.bytes_acked, 16 * 3);
        assert_eq!(s.bytes_nacked, 0);
    }

    /// Wrong slave address NACKs and transitions to Ignored;
    /// subsequent payload bytes don't accidentally re-address
    /// the slave.
    #[test]
    fn wrong_slave_address_nacks_and_ignores_payload() {
        let mut s = Src4382::default();
        s.on_start();
        assert!(!s.consume_tx_byte(0x68), "TAS3108's address must NACK");
        // SRC4382 stays Ignored until the next START.
        assert!(!s.consume_tx_byte(0xE2));
        assert!(!s.consume_tx_byte(0x05));
        s.on_start();
        assert!(s.consume_tx_byte(0xE2), "fresh START re-arms the slave");
    }

    /// Random-read sequence
    /// (`src/dlcp_fw/asm/dlcp_main_v32.asm:7181`):
    /// `START | 0xE2 | subaddr | RepeatedStart | 0xE3 | <byte>`.
    /// The slave returns the byte at the latched subaddress.
    #[test]
    fn random_read_returns_latched_register() {
        let mut s = Src4382::default();
        // Pre-load register 0x12 (non-PCM detection) with
        // simulated "no input" status.
        s.poke_subaddr(0x12, 0xA5);

        // Set up subaddress phase.
        s.on_start();
        assert!(s.consume_tx_byte(0xE2));
        assert!(s.consume_tx_byte(0x12));
        // Repeated-start, switch to read.
        s.on_repeated_start();
        assert!(s.consume_tx_byte(0xE3));
        // Slave drives a byte.
        assert_eq!(s.provide_rx_byte(), 0xA5);
        s.on_stop();
    }

    /// Read-before-any-latch is rejected with NACK + Ignored
    /// (same strict-misuse shape as TAS3108).
    #[test]
    fn read_before_any_subaddress_latched_nacks() {
        let mut s = Src4382::default();
        s.on_start();
        assert!(!s.consume_tx_byte(0xE3));
    }
}
