//! TAS3108 audio DSP I²C slave model.
//!
//! Phase-3.5 minimum-viable slave to unblock V3.1 MAIN's
//! `dsp_ping` and `volume_dsp_write` paths in the chain
//! parity test.  The TAS3108 is the audio DSP wired to MAIN's
//! MSSP I²C bus; without a model, MAIN's master-mode TX bytes
//! get NACKed (no slave on the bus) and MAIN spin-retries
//! forever in `wait_bf_clear_loop`.
//!
//! ## Reference
//!
//! `firmware/reference/tas3108.md` (datasheet companion,
//! authoritative per `CLAUDE.md`).  Key sections:
//!
//! * §6.2 (lines 581-641): I²C subaddress access protocol,
//!   slave-address table.
//! * Slave addresses (Tbl 6-1): `0x68 / 0x69 / 0x6A / 0x6B`
//!   selected by hardware pin `CS0` (0 -> 0x68/0x69; 1 ->
//!   0x6A/0x6B).  Pulldown default makes CS0 = 0.
//! * Broadcast address `0x00` is also ACKed (line 585).
//! * §6.2.1 (line 665): write transactions -- subaddress is
//!   the first data byte after the slave-write address; data
//!   bytes follow; sequential addressing auto-increments.
//! * §6.2.2 (line 643): read transactions -- master writes
//!   subaddress first, then issues a Repeated-Start with the
//!   slave-read address and clocks out data bytes.
//!
//! ## Phase-3.5 scope
//!
//! Models enough state to ACK V3.1 MAIN's:
//!
//! * `dsp_ping` (sends address byte 0x68, expects ACK).
//! * `volume_dsp_write` (sends 0x68 + subaddress 0x30 + 4
//!   coefficient bytes, expects ACK on every byte).
//!
//! Storage: a 256-byte register file indexed by 8-bit
//! subaddress.  Sequential writes auto-increment the
//! subaddress per §6.2.1.  Read protocol (§6.2.2) and
//! sequential-write 5-word commit-or-discard rule are
//! deferred -- V3.1's boot path doesn't exercise them.
//!
//! ## What this file does NOT cover
//!
//! * Audio DSP function -- coefficients are stored but not
//!   acted on.  Test parity is byte-level over I²C.
//! * I²C master mode (TAS3108 reading from external EEPROM
//!   per §6.3 -- not needed; V3.1's chain doesn't have an
//!   EEPROM-shared bus).
//! * Status register `0x02` semantics -- reads return zero
//!   (no error).  V3.1 doesn't appear to poll it pre-chain.

#![allow(
    dead_code,
    reason = "Phase-3.5 scaffold; chain wiring lands in a follow-up commit"
)]

use serde::{Deserialize, Serialize};

/// One-byte broadcast address (datasheet line 585).
const BROADCAST_ADDR: u8 = 0x00;

/// Number of subaddresses the slave's register file covers.
/// 8-bit subaddress space per §6.2 -- 256 entries.
const SUBADDR_COUNT: usize = 256;

/// I²C transaction phase.
#[derive(Serialize, Deserialize, Copy, Clone, Debug, PartialEq, Eq)]
enum Phase {
    /// No transaction in progress.  The next byte from the
    /// master is interpreted as the slave-address byte.
    Idle,
    /// Address byte didn't match this slave; the slave is
    /// "off the bus" for the current transaction and
    /// drops every subsequent byte (no ACK, no state
    /// transitions on `consume_tx_byte`).  Only `on_start`
    /// / `on_stop` / `on_repeated_start` clear this state
    /// -- mirrors real silicon, where a slave that NACKed
    /// the address phase stays quiet until the master
    /// issues a fresh START.  Without this state, a multi-
    /// slave bus can spuriously address a NACKing slave
    /// when a later data byte happens to match its
    /// address (codex review of 167ee52).
    Ignored,
    /// Address matched with R/W = write.  The next byte is
    /// the subaddress (first data byte of a write
    /// transaction per §6.2.1).
    AwaitingSubaddress,
    /// Inside a write transaction; subaddress already
    /// latched.  Subsequent bytes are data; subaddress
    /// auto-increments per §6.2.1's sequential rule.
    Writing { next_subaddr: u8 },
    /// Address matched with R/W = read.  The next master TX
    /// is normally an ACK/NACK for a slave-driven byte; the
    /// slave provides bytes via [`Tas3108::provide_rx_byte`]
    /// starting at the latched subaddress.  Phase-3.5 leaves
    /// this stub-level (V3.1 boot doesn't read the DSP).
    Reading { next_subaddr: u8 },
}

impl Default for Phase {
    fn default() -> Self {
        Phase::Idle
    }
}

/// One completed master-write transaction to the TAS3108.
///
/// This is intentionally higher level than the byte-addressed register
/// file: DLCP preset entries write a logical subaddress plus a 4- or
/// 20-byte payload.  The final byte stored at a subaddress is too lossy
/// to prove that the real LX521 coefficient payload reached the DSP, so
/// tests use this log to compare the exact payload sent by firmware.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, Eq)]
pub struct Tas3108WriteTransaction {
    pub start_subaddr: u8,
    pub payload: Vec<u8>,
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, Eq)]
struct Tas3108WriteInProgress {
    start_subaddr: u8,
    payload: Vec<u8>,
}

/// TAS3108 audio-DSP I²C slave.
#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct Tas3108 {
    /// Hardware-pin chip-select.  Selects between
    /// 0x68/0x69 (CS0 = false) and 0x6A/0x6B (CS0 = true)
    /// per Tbl 6-1.  Wired to GND on the DLCP board, so the
    /// default constructor uses `false`.
    cs0: bool,
    /// 256-byte register file indexed by subaddress.  Reads
    /// of unwritten subaddresses return 0.
    #[serde(with = "crate::serde_helpers::boxed_big_array")]
    regs: Box<[u8; SUBADDR_COUNT]>,
    /// Most-recently-latched subaddress (post-`AwaitingSubaddress`).
    /// Persists across STOPs so a write followed by a
    /// repeated-start read can reuse it (§6.2 read protocol).
    /// `None` until the master issues a write transaction
    /// with a subaddress -- a read attempt before any latch
    /// gets NACKed (real silicon would drive whatever
    /// random data the internal subaddress register held;
    /// our model is intentionally stricter so misuse
    /// surfaces loudly during chain-parity work).
    last_latched_subaddr: Option<u8>,
    /// Current transaction state.
    phase: Phase,
    /// Diagnostic counters.  Used by chain-level integration
    /// tests to assert specific traffic shapes (e.g. "MAIN
    /// completed exactly N writes to subaddress 0x30").
    pub bytes_acked: u64,
    pub bytes_nacked: u64,
    /// Completed write transactions, preserving the start
    /// subaddress and entire data payload for each STOP-terminated
    /// write.  This is simulator observability only; the byte register
    /// file remains the compatibility surface for older tests.
    write_log: Vec<Tas3108WriteTransaction>,
    /// Current write payload being accumulated between subaddress
    /// latch and transaction termination.
    current_write: Option<Tas3108WriteInProgress>,
    /// Fault-injection: remaining count of address-phase
    /// NACKs.  When `> 0`, the slave NACKs its own write/read
    /// address byte (transitioning to `Ignored` for the rest
    /// of the transaction) and decrements.  Mirror of gpsim's
    /// `i2c-regfile.Address_Nack_Count` knob exposed by
    /// `MainChainHarness.set_i2c_fault(device, address_nack_
    /// count=N)` (chain_gpsim.py:471).  Only the device's own
    /// addresses are NACKed; broadcast (0x00) and other
    /// addresses still take their default code paths.  Set to
    /// 0 to clear; defaults to 0 (no fault).
    address_nack_count_remaining: u32,
}

impl Default for Tas3108 {
    fn default() -> Self {
        Self::new(false)
    }
}

impl Tas3108 {
    /// Construct a fresh TAS3108 slave with the given CS0
    /// pin state.  All registers are zero-initialised; no
    /// transaction is in progress.
    pub fn new(cs0: bool) -> Self {
        Tas3108 {
            cs0,
            regs: Box::new([0u8; SUBADDR_COUNT]),
            last_latched_subaddr: None,
            phase: Phase::Idle,
            bytes_acked: 0,
            bytes_nacked: 0,
            write_log: Vec::new(),
            current_write: None,
            address_nack_count_remaining: 0,
        }
    }

    /// Program the fault-injection address-NACK counter.
    /// While `count > 0`, every address-phase byte that
    /// matches the slave's own write or read address is
    /// NACKed (the slave transitions to `Ignored` for the
    /// rest of that transaction) and the counter is
    /// decremented.  Used to simulate persistent DSP
    /// unresponsiveness for the V3.1 robustness tests
    /// (test_v31_review_findings.py).
    ///
    /// Mirror of gpsim's
    /// `i2c-regfile.Address_Nack_Count` knob exposed by
    /// `MainChainHarness.set_i2c_fault(device,
    /// address_nack_count=N)` (chain_gpsim.py:471).
    pub fn set_address_nack_count(&mut self, count: u32) {
        self.address_nack_count_remaining = count;
    }

    /// Read the remaining address-NACK injections.  Mirror of
    /// gpsim's `read_i2c_attribute("dsp34", "Address_Nack_Count")`
    /// which returns the gpsim regfile module's current
    /// remaining count.  Used by deafness-chain regression
    /// tests that assert NACKs were CONSUMED by firmware-driven
    /// I²C bursts (i.e. the count went down between
    /// `set_address_nack_count(N)` and the post-burst read).
    pub fn address_nack_count_remaining(&self) -> u32 {
        self.address_nack_count_remaining
    }

    /// Clear all fault-injection counters back to their
    /// default (no-fault) state.  Mirror of
    /// `MainChainHarness.clear_i2c_faults` (chain_gpsim.py:526),
    /// which resets address-NACK and the (not-yet-modeled)
    /// stretch / data-NACK / stuck-SDA knobs.
    pub fn clear_i2c_faults(&mut self) {
        self.address_nack_count_remaining = 0;
    }

    /// Slave-address byte the master must use to ADDRESS this
    /// device for a write transaction.  Read-address is
    /// `write_address() | 1`.
    pub fn write_address(&self) -> u8 {
        if self.cs0 { 0x6A } else { 0x68 }
    }

    /// Read the byte currently stored at `subaddr`.  Returns
    /// 0 for unwritten subaddresses (the register file is
    /// zero-initialised).  Useful for asserting that a
    /// firmware-side I²C write actually committed.
    pub fn read_subaddr(&self, subaddr: u8) -> u8 {
        self.regs[subaddr as usize]
    }

    /// Return the most recent completed write payload that started at
    /// `subaddr`, if any.  Used by Python-facing release tests to assert
    /// exact preset-table payload delivery.
    pub fn last_write_payload(&self, subaddr: u8) -> Option<&[u8]> {
        self.write_log
            .iter()
            .rev()
            .find(|tx| tx.start_subaddr == subaddr)
            .map(|tx| tx.payload.as_slice())
    }

    /// Completed write transaction log.
    pub fn write_log(&self) -> &[Tas3108WriteTransaction] {
        &self.write_log
    }

    /// Clear completed write observability without changing register
    /// contents or transaction state.
    pub fn reset_write_log(&mut self) {
        self.write_log.clear();
    }

    /// Reset transaction state on a master-issued START.  The
    /// next [`consume_tx_byte`] is interpreted as a slave-
    /// address byte.  Caller (chain dispatcher) invokes this
    /// when MSSP completes its Start-condition state.
    pub fn on_start(&mut self) {
        self.finish_current_write();
        self.phase = Phase::Idle;
    }

    /// Reset transaction state on a master-issued STOP.  Same
    /// effect as `on_start` -- both terminate the current
    /// transaction.  Defined separately for parity with the
    /// MSSP state machine's `complete_start` /
    /// `complete_stop` hooks.
    pub fn on_stop(&mut self) {
        self.finish_current_write();
        self.phase = Phase::Idle;
    }

    /// Master-issued Repeated-Start.  Per §6.2 the
    /// subaddress already latched in a prior write
    /// transaction is preserved; the slave just re-enters
    /// "expect address byte" state.  Equivalent to
    /// `on_start` in this Phase-3.5 model.
    pub fn on_repeated_start(&mut self) {
        self.finish_current_write();
        self.phase = Phase::Idle;
    }

    /// Consume a master-driven TX byte.  Returns `true` if
    /// the slave ACKs (master should clear ACKSTAT), `false`
    /// for NACK.
    ///
    /// State machine:
    ///   * `Idle`  -> address byte; ACK if matches our
    ///     own write/read address or the broadcast address
    ///     (0x00).
    ///   * `AwaitingSubaddress` -> subaddress byte; latch and
    ///     transition to Writing.
    ///   * `Writing` -> data byte; commit to the register
    ///     file at `next_subaddr`; auto-increment per
    ///     §6.2.1.
    ///   * `Reading` -> in this phase the master ACKs slave-
    ///     driven bytes via `provide_rx_byte`.  TX bytes
    ///     during a read transaction shouldn't happen on a
    ///     well-behaved bus; NACK to surface the misuse.
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
        // Fault-injection: NACK our own write/read address
        // while the address-NACK counter is non-zero.  The
        // slave goes Ignored for the rest of the transaction
        // (subsequent payload bytes don't re-address us;
        // `on_start`/`on_stop` clear back to `Idle`).
        // Broadcast (0x00) and other addresses are unaffected
        // -- mirrors gpsim's per-device `Address_Nack_Count`,
        // which only NACKs the device's own slave addresses.
        if self.address_nack_count_remaining > 0 && (byte == write_addr || byte == read_addr) {
            self.address_nack_count_remaining -= 1;
            self.phase = Phase::Ignored;
            return false;
        }
        if byte == write_addr {
            // Master is starting a write transaction.  The
            // next byte is the subaddress (§6.2.1).
            self.phase = Phase::AwaitingSubaddress;
            true
        } else if byte == read_addr {
            // Master is starting a read transaction.  Per
            // §6.2 read protocol, the master must have
            // previously issued a write transaction (or a
            // write-then-repeated-start preamble) to latch
            // the starting subaddress.  Reject the read with
            // a NACK if no subaddress has ever been latched
            // -- real silicon would return whatever random
            // data the internal subaddress register held;
            // our model is intentionally stricter so misuse
            // surfaces loudly during chain-parity work.
            // Reference: codex review of 5330a68 LOW #1.
            match self.last_latched_subaddr {
                Some(start) => {
                    self.phase = Phase::Reading {
                        next_subaddr: start,
                    };
                    true
                }
                None => {
                    // Same Ignored-on-NACK rule as the
                    // address-mismatch branch below: a NACKing
                    // slave must stay quiet for the rest of
                    // the transaction, not re-process later
                    // bytes as fresh address candidates.
                    self.phase = Phase::Ignored;
                    false
                }
            }
        } else if byte == BROADCAST_ADDR {
            // §6.2 line 585: broadcast address ACKed.  Treat
            // as a write transaction since broadcast reads
            // are nonsensical and the firmware doesn't issue
            // them.
            self.phase = Phase::AwaitingSubaddress;
            true
        } else {
            // Address mismatch: NACK and transition to
            // Ignored so subsequent payload bytes from this
            // transaction don't accidentally re-address us.
            // `on_start` / `on_stop` / `on_repeated_start`
            // clear Ignored back to Idle.
            self.phase = Phase::Ignored;
            false
        }
    }

    fn handle_subaddress_byte(&mut self, byte: u8) -> bool {
        self.last_latched_subaddr = Some(byte);
        self.finish_current_write();
        self.current_write = Some(Tas3108WriteInProgress {
            start_subaddr: byte,
            payload: Vec::new(),
        });
        self.phase = Phase::Writing { next_subaddr: byte };
        true
    }

    fn handle_write_data_byte(&mut self, byte: u8, next_subaddr: u8) -> bool {
        self.regs[next_subaddr as usize] = byte;
        if let Some(tx) = &mut self.current_write {
            tx.payload.push(byte);
        }
        // Per §6.2.1 sequential addressing: subaddress auto-
        // increments after every data byte written.  Wraps
        // mod 256 because the subaddress is 8-bit.
        self.phase = Phase::Writing {
            next_subaddr: next_subaddr.wrapping_add(1),
        };
        true
    }

    fn finish_current_write(&mut self) {
        if let Some(tx) = self.current_write.take() {
            if !tx.payload.is_empty() {
                self.write_log.push(Tas3108WriteTransaction {
                    start_subaddr: tx.start_subaddr,
                    payload: tx.payload,
                });
            }
        }
    }

    /// True iff the slave is currently in a read transaction
    /// (`Phase::Reading`).  The chain dispatcher uses this to
    /// pick the slave that should drive the next master-RX
    /// byte: at most one slave is `Reading` at any time on a
    /// well-formed bus, so the dispatcher iterates coupled
    /// slaves and takes the first that returns true.
    /// `pub(crate)` because the only consumer is the chain
    /// dispatcher in `crate::chain`; external callers should
    /// drive the read transaction via `provide_rx_byte()`.
    pub(crate) fn is_reading(&self) -> bool {
        matches!(self.phase, Phase::Reading { .. })
    }

    /// Provide one byte for a master-driven read.  Returns
    /// the register-file byte at the current subaddress and
    /// auto-increments per §6.2.2.  Returns 0 if no read
    /// transaction is in progress (defensive; chain
    /// dispatcher should only call this in response to MSSP
    /// completing an RxByte while a read transaction is
    /// active on this slave).
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

    /// V3.1's `dsp_ping` (firmware/patched/releases/DLCP_Firmware_V3.1.lst:7802):
    /// Master sends START + 0x68 + STOP and checks ACKSTAT.
    /// Default-CS0 slave must ACK 0x68.
    #[test]
    fn dsp_ping_address_byte_is_acked() {
        let mut dsp = Tas3108::default();
        dsp.on_start();
        assert!(dsp.consume_tx_byte(0x68), "dsp_ping address byte must ACK");
        dsp.on_stop();
        assert_eq!(dsp.bytes_acked, 1);
        assert_eq!(dsp.bytes_nacked, 0);
    }

    /// Fault-injection: while `set_address_nack_count(N)` is
    /// non-zero, the slave NACKs its own write and read
    /// addresses and decrements the counter.  Once the
    /// counter reaches 0, normal ACK behaviour resumes.
    /// Mirrors gpsim's `i2c-regfile.Address_Nack_Count` per-
    /// device knob exposed by
    /// `MainChainHarness.set_i2c_fault(device,
    /// address_nack_count=N)` (chain_gpsim.py:471).
    #[test]
    fn address_nack_counter_nacks_then_recovers() {
        let mut dsp = Tas3108::default();
        dsp.set_address_nack_count(2);

        // First address byte: NACKed.
        dsp.on_start();
        assert!(!dsp.consume_tx_byte(0x68), "first address must NACK");
        dsp.on_stop();
        assert_eq!(dsp.bytes_nacked, 1);

        // Second address byte (read direction): NACKed too.
        dsp.on_start();
        assert!(
            !dsp.consume_tx_byte(0x69),
            "second address (read) must NACK"
        );
        dsp.on_stop();
        assert_eq!(dsp.bytes_nacked, 2);

        // Third address byte: counter exhausted, normal ACK.
        dsp.on_start();
        assert!(
            dsp.consume_tx_byte(0x68),
            "third address must ACK after counter exhausted"
        );
        dsp.on_stop();
        assert_eq!(dsp.bytes_acked, 1);
    }

    /// Fault-injection: broadcast (0x00) and other (mismatched)
    /// addresses are NOT affected by the address-NACK counter.
    /// Broadcast still ACKs; non-matching addresses still NACK
    /// silently without touching the counter.
    #[test]
    fn address_nack_counter_only_targets_own_addresses() {
        let mut dsp = Tas3108::default();
        dsp.set_address_nack_count(5);

        // Broadcast: ACKed; counter untouched.
        dsp.on_start();
        assert!(
            dsp.consume_tx_byte(0x00),
            "broadcast must ACK regardless of fault"
        );
        dsp.on_stop();

        // Non-matching address (0xA0): NACKed-as-Ignored, but
        // not counted against the address-NACK counter (no
        // decrement).
        dsp.on_start();
        assert!(
            !dsp.consume_tx_byte(0xA0),
            "non-matching address always NACKs"
        );
        dsp.on_stop();

        // Counter is still 5 -- own write address still NACKs.
        dsp.on_start();
        assert!(
            !dsp.consume_tx_byte(0x68),
            "own address must still NACK (counter 5 -> 4)"
        );
        dsp.on_stop();

        // clear_i2c_faults zeroes the counter.
        dsp.clear_i2c_faults();
        dsp.on_start();
        assert!(dsp.consume_tx_byte(0x68), "post-clear, own address ACKs");
        dsp.on_stop();
    }

    /// V3.1's `volume_dsp_write` (lst:7838): Master sends
    /// START + 0x68 + 0x30 (subaddress) + 4 coefficient
    /// bytes + STOP.  Slave must ACK every byte and the four
    /// coefficient bytes must land at subaddresses 0x30..0x34.
    #[test]
    fn volume_dsp_write_six_byte_burst_lands_at_subaddr_30() {
        let mut dsp = Tas3108::default();
        dsp.on_start();
        assert!(dsp.consume_tx_byte(0x68));
        assert!(dsp.consume_tx_byte(0x30));
        assert!(dsp.consume_tx_byte(0xDE));
        assert!(dsp.consume_tx_byte(0xAD));
        assert!(dsp.consume_tx_byte(0xBE));
        assert!(dsp.consume_tx_byte(0xEF));
        dsp.on_stop();
        assert_eq!(dsp.read_subaddr(0x30), 0xDE);
        assert_eq!(dsp.read_subaddr(0x31), 0xAD);
        assert_eq!(dsp.read_subaddr(0x32), 0xBE);
        assert_eq!(dsp.read_subaddr(0x33), 0xEF);
        assert_eq!(
            dsp.last_write_payload(0x30),
            Some([0xDE, 0xAD, 0xBE, 0xEF].as_slice())
        );
        assert_eq!(dsp.write_log().len(), 1);
        assert_eq!(dsp.bytes_acked, 6);
    }

    /// Wrong slave address NACKs and stays Idle so a
    /// subsequent transaction can re-address correctly.
    #[test]
    fn wrong_slave_address_nacks() {
        let mut dsp = Tas3108::default();
        dsp.on_start();
        assert!(!dsp.consume_tx_byte(0x42), "wrong address must NACK");
        // Subsequent re-address ACKs.
        dsp.on_start();
        assert!(dsp.consume_tx_byte(0x68));
        assert_eq!(dsp.bytes_acked, 1);
        assert_eq!(dsp.bytes_nacked, 1);
    }

    /// Broadcast address (§6.2 line 585) ACKed.
    #[test]
    fn broadcast_address_acks() {
        let mut dsp = Tas3108::default();
        dsp.on_start();
        assert!(dsp.consume_tx_byte(0x00));
        // Following byte is treated as a subaddress, then
        // data: data lands at the broadcast subaddress.
        assert!(dsp.consume_tx_byte(0x55));
        assert!(dsp.consume_tx_byte(0xAA));
        dsp.on_stop();
        assert_eq!(dsp.read_subaddr(0x55), 0xAA);
    }

    /// CS0=1 selects 0x6A/0x6B; the default 0x68 must NACK.
    #[test]
    fn cs0_high_selects_6a() {
        let mut dsp = Tas3108::new(true);
        assert_eq!(dsp.write_address(), 0x6A);
        dsp.on_start();
        assert!(!dsp.consume_tx_byte(0x68), "CS0=1 must NACK 0x68");
        dsp.on_start();
        assert!(dsp.consume_tx_byte(0x6A));
    }

    /// Sequential write per §6.2.1: subaddress auto-
    /// increments across multiple data bytes.  Two
    /// transactions, the second one re-uses the latched
    /// subaddress only after a fresh address+subaddress
    /// preamble (random addressing semantics).
    #[test]
    fn sequential_write_auto_increments_subaddress() {
        let mut dsp = Tas3108::default();
        dsp.on_start();
        assert!(dsp.consume_tx_byte(0x68));
        assert!(dsp.consume_tx_byte(0x80)); // subaddr
        for offset in 0..16u8 {
            assert!(dsp.consume_tx_byte(0xC0 + offset));
        }
        dsp.on_stop();
        for offset in 0..16u8 {
            assert_eq!(
                dsp.read_subaddr(0x80 + offset),
                0xC0 + offset,
                "byte #{offset} must land at subaddress 0x{:02X}",
                0x80 + offset
            );
        }
    }

    /// Read transaction (master sends `0x69` for read
    /// address): slave returns whatever's at the last
    /// latched subaddress and auto-increments.
    #[test]
    fn read_transaction_returns_register_file_bytes() {
        let mut dsp = Tas3108::default();
        // Pre-populate via a write.
        dsp.on_start();
        dsp.consume_tx_byte(0x68);
        dsp.consume_tx_byte(0x40); // subaddr
        dsp.consume_tx_byte(0x11);
        dsp.consume_tx_byte(0x22);
        dsp.on_stop();
        // Master starts a read: STOP wasn't issued in real
        // firmware (a Repeated-Start follows), but on_stop +
        // on_start + read-address has the same net effect on
        // the slave's phase machine.
        dsp.on_repeated_start();
        // Note: after the previous write, subaddress was
        // auto-incremented past the last write byte.  The
        // master sets the read start point by re-issuing a
        // subaddress-write before the repeated-start.  In
        // this terse test we directly seed via the previous
        // write's last_latched_subaddr.  V3.1 doesn't
        // exercise this path; this test is sanity-only.
        assert!(dsp.consume_tx_byte(0x69)); // read address
        assert_eq!(dsp.provide_rx_byte(), dsp.regs[0x40]);
        assert_eq!(dsp.provide_rx_byte(), dsp.regs[0x41]);
    }

    /// `on_start` is idempotent: calling it twice is the
    /// same as calling it once.  Useful for re-entering
    /// transaction state after a parser-side error or NACK.
    #[test]
    fn on_start_is_idempotent() {
        let mut dsp = Tas3108::default();
        dsp.on_start();
        dsp.on_start();
        assert!(dsp.consume_tx_byte(0x68));
    }

    /// V3.1's biquad-table write path
    /// (`firmware/patched/releases/DLCP_Firmware_V3.1.lst:5099`+
    /// in `main_i2c_service_381c`): write 20 data bytes to a
    /// biquad subaddress (5×32-bit coefficient words per
    /// entry, per datasheet §6.2.1).  The slave must ACK
    /// every byte and the data must land at the correct
    /// auto-incrementing subaddresses.  Phase-3.5 scope:
    /// the complete-or-discard rule for truncated bursts is
    /// deferred (task #24); this test covers the happy path
    /// V3.1 actually exercises.
    #[test]
    fn biquad_subaddress_write_covers_20_bytes_per_entry() {
        let mut dsp = Tas3108::default();
        dsp.on_start();
        assert!(dsp.consume_tx_byte(0x68));
        assert!(dsp.consume_tx_byte(0x37)); // first biquad subaddr
        let coeffs: Vec<u8> = (0..20u8).map(|i| 0xA0 ^ i).collect();
        for &b in &coeffs {
            assert!(dsp.consume_tx_byte(b), "every biquad data byte must ACK");
        }
        dsp.on_stop();
        for (offset, &b) in coeffs.iter().enumerate() {
            assert_eq!(
                dsp.read_subaddr(0x37 + offset as u8),
                b,
                "biquad byte #{offset} must land at subaddr 0x{:02X}",
                0x37 + offset,
            );
        }
        assert_eq!(dsp.bytes_acked, 22); // address + subaddr + 20 data
    }

    /// LOW from codex review of 167ee52: after a NACK on the
    /// address phase, the slave must drop subsequent payload
    /// bytes (Ignored state) instead of staying Idle and
    /// re-interpreting later data bytes as fresh addresses.
    /// On a multi-slave bus, a data byte that happens to
    /// match this slave's address would otherwise spuriously
    /// trigger a transaction.
    #[test]
    fn nacked_slave_ignores_payload_until_next_start() {
        let dsp = Tas3108::default();
        // Slave A's address is 0x68; we simulate slave B
        // (CS0=true -> 0x6A) seeing the same bus traffic
        // intended for slave A.  Slave B should NACK the
        // 0x68 address and IGNORE subsequent bytes -- even
        // if they include 0x6A (its own address) as
        // subaddress or data.
        let mut slave_b = Tas3108::new(true);
        slave_b.on_start();
        // Slave B: address byte 0x68 is not its (0x6A) -> NACK
        assert!(!slave_b.consume_tx_byte(0x68));
        // Slave A's transaction continues with data 0x6A as a
        // SUBADDRESS or DATA byte.  Slave B must NOT reawaken.
        assert!(
            !slave_b.consume_tx_byte(0x6A),
            "ignored slave must not re-address"
        );
        assert!(!slave_b.consume_tx_byte(0xAA));
        slave_b.on_stop();
        // After the next START, slave B's state is reset
        // and addressing 0x6A ACKs again.
        slave_b.on_start();
        assert!(slave_b.consume_tx_byte(0x6A));
        // Sanity: dsp (slave A) keeps independent state.
        let _ = dsp.write_address();
    }

    /// LOW from codex review of 5330a68: a master that issues
    /// a read address (`0x69`) BEFORE any subaddress has ever
    /// been latched must NACK -- per §6.2 read protocol the
    /// subaddress is supplied by a prior write transaction
    /// (or a write-then-repeated-start preamble).  Real
    /// silicon would drive whatever random data is in its
    /// internal subaddress register; we intentionally NACK
    /// to surface chain-parity bugs loudly.
    #[test]
    fn read_address_before_any_subaddress_latched_nacks() {
        let mut dsp = Tas3108::default();
        dsp.on_start();
        assert!(
            !dsp.consume_tx_byte(0x69),
            "read without prior latch must NACK"
        );
        // After a write transaction sets the subaddress, a
        // subsequent read at 0x69 ACKs.
        dsp.on_start();
        assert!(dsp.consume_tx_byte(0x68));
        assert!(dsp.consume_tx_byte(0x40));
        dsp.on_repeated_start();
        assert!(dsp.consume_tx_byte(0x69), "read after latch must ACK");
    }
}
