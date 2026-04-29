//! MSSP (Master Synchronous Serial Port) — I²C master mode
//! Phase-2 minimal model.
//!
//! ## Scope
//!
//! Only I²C master mode is modelled (V3.2 MAIN talks to the
//! TAS3108 DSP via I²C; CONTROL doesn't use this peripheral).
//! The minimum-viable peripheral for Phase 2 covers:
//!
//!   * SFR write masks (SSPCON1 / SSPCON2 / SSPSTAT bit-by-bit
//!     read-only-ness per DS40001303H Reg 17-2/17-3/17-4).
//!   * Read-only-status-bit preservation (SSPSTAT.BF, .R/W,
//!     .S, .P, .D/A on writes; SSPCON1.WCOL/SSPOV are SW
//!     read-only-clearable error flags).
//!   * Master-mode start/stop/restart sequence trigger
//!     observation: SEN/PEN/RSEN bit transitions in
//!     SSPCON2 schedule a state-machine advance.
//!   * Bit-level SCL clock generation from SSPADD divisor:
//!     `Fbus = Fcy / (4 × (SSPADD + 1))`.  SSPADD=0x77 ->
//!     33.3 kHz on 16 MHz Fosc per spec §6.
//!   * BF (Buffer Full) flag tracking on SSPBUF write (TX)
//!     and read.
//!
//! ## Out of scope (Phase 3+)
//!
//!   * Slave-mode behaviour (MAIN is always master in DLCP).
//!   * Actual bus-level bit shifting against a peer device:
//!     the I²C bus is a pin-network artefact (Phase 3) -- the
//!     Phase-2 model just tracks state-machine transitions
//!     and the BF/SSPIF flags so firmware that polls them
//!     advances correctly.
//!   * Bus-collision detection (BCLIE / BCLIF) -- needs the
//!     pin network.
//!   * The 10-bit-address mode and General Call address path.
//!
//! ## Master-mode trigger semantics (DS §17.4)
//!
//! Each transfer-control bit in SSPCON2 schedules an
//! independent fixed-duration sequence on the bus.  Real
//! silicon enforces "lower SSPCON2 event bits may not be set
//! while the I²C module is not idle".  Triggers:
//!
//!   * `SEN`  -> Start  condition (≈ 1 SCL period; bit clears
//!     when complete; SSPIF asserts).
//!   * `RSEN` -> Repeated-start condition (≈ 1 SCL period; same
//!     auto-clear + SSPIF).
//!   * `PEN`  -> Stop   condition (≈ 1 SCL period; same).
//!   * `RCEN` -> Receive enable (8 SCL periods of input shift
//!     + ACK; SSPBUF loads with the byte; BF asserts; SSPIF
//!     asserts).
//!   * SSPBUF write -> Transmit byte (8 SCL periods of output
//!     shift + ACK; BF clears; SSPIF asserts; SSPCON2.ACKSTAT
//!     reflects slave-ACK absence as 1 in this Phase-2
//!     bus-less model).
//!
//! All triggers are gated on (SSPEN ∧ SSPM<3:0> = 1000) and
//! ignored if the state machine is not Idle.
//!
//! ## SFR addresses (DS40001303H Tbl 5-1)
//!
//! | Addr  | Reg     | Role                                |
//! |-------|---------|-------------------------------------|
//! | 0xFC9 | SSPBUF  | Shift FIFO data byte (SW R/W)        |
//! | 0xFC8 | SSPADD  | Baud divisor (master) / address (slave) |
//! | 0xFC7 | SSPSTAT | SMP/CKE/D-A/P/S/R-W/UA/BF             |
//! | 0xFC6 | SSPCON1 | WCOL/SSPOV/SSPEN/CKP/SSPM<3:0>        |
//! | 0xFC5 | SSPCON2 | GCEN/ACKSTAT/ACKDT/ACKEN/RCEN/PEN/RSEN/SEN |
//! | 0xFC4 | (ADRESH on K20 -- not MSSP)            |
//! | 0xF77 | SSPMSK  | I²C address mask                      |
//!
//! PIR1 bit 3 = SSPIF.  PIE1 bit 3 = SSPIE.
//!
//! ## Phase-2 state machine
//!
//! ```text
//!     Idle ─SEN─▶ StartScheduled ─(scl_period)─▶ AddrShift
//!     AddrShift ─(8 × scl_bit)─▶ AckPhase
//!     AckPhase ─(scl_period)─▶ DataShift
//!     DataShift ─(8 × scl_bit)─▶ AckPhase or StopScheduled
//!     StopScheduled (PEN=1) ─(scl_period)─▶ Idle
//! ```
//!
//! Bus-side responses (slave ACK / data) are absent in
//! Phase 2 -- the master sees NACK on every transfer
//! attempt unless explicitly faked by a test.  Phase 4 dual-
//! run will replay gpsim's exact timing.

use crate::memory::{Memory, Variant};

pub const SSPBUF_ADDR: u16 = 0xFC9;
pub const SSPADD_ADDR: u16 = 0xFC8;
pub const SSPSTAT_ADDR: u16 = 0xFC7;
pub const SSPCON1_ADDR: u16 = 0xFC6;
pub const SSPCON2_ADDR: u16 = 0xFC5;
pub const SSPMSK_ADDR: u16 = 0xF77;
pub const PIR1_ADDR: u16 = 0xF9E;

const SSPSTAT_BF: u8 = 1 << 0;
const SSPCON1_WCOL: u8 = 1 << 7;
const SSPCON1_SSPEN: u8 = 1 << 5;
const SSPCON1_SSPM_MASK: u8 = 0x0F;
const SSPCON2_SEN: u8 = 1 << 0;
const SSPCON2_RSEN: u8 = 1 << 1;
const SSPCON2_PEN: u8 = 1 << 2;
const SSPCON2_RCEN: u8 = 1 << 3;
const SSPCON2_ACKEN: u8 = 1 << 4;
const SSPCON2_ACKSTAT: u8 = 1 << 6;
const SSPCON2_ALL_TRIGGERS: u8 =
    SSPCON2_SEN | SSPCON2_RSEN | SSPCON2_PEN | SSPCON2_RCEN | SSPCON2_ACKEN;
const PIR1_SSPIF: u8 = 1 << 3;

/// I²C master-mode SSPCON1<3:0> SSPM encoding.  Per DS Tbl
/// 17-1 only `1000` selects "I²C Master mode, clock = Fosc /
/// (4 × (SSPADD + 1))".  Other modes (0110/0111 = 7-bit/
/// 10-bit slave; 1011/1110/1111 = firmware-controlled-master
/// variants) aren't modelled in Phase 2.
const SSPM_I2C_MASTER: u8 = 0b1000;

/// Each variant is "Tcy remaining until this transfer ends".
/// On reaching 0 the state-machine fan-out clears the
/// triggering bit (SEN/RSEN/PEN/RCEN/ACKEN/SSPBUF) and
/// asserts SSPIF.
#[derive(Clone, Debug, PartialEq, Eq)]
enum I2cState {
    Idle,
    /// SEN-driven start condition in flight.
    Start(u32),
    /// RSEN-driven repeated-start condition in flight.
    RepeatedStart(u32),
    /// PEN-driven stop condition in flight.
    Stop(u32),
    /// SSPBUF-write-driven 8-bit transmit + ACK in flight.
    TxByte(u32),
    /// RCEN-driven 8-bit receive + ACK in flight.
    RxByte(u32),
    /// ACKEN-driven master-ACK pulse in flight.
    AckPulse(u32),
}

impl Default for I2cState {
    fn default() -> Self {
        I2cState::Idle
    }
}

/// One completed bus-level I²C event that the chain
/// dispatcher can route to coupled slaves.  Drained from
/// `Mssp::take_last_bus_event` once per tick.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum I2cBusEvent {
    /// Master-issued Start condition completed.
    Start,
    /// Master-issued Repeated-Start completed.
    RepeatedStart,
    /// Master-issued Stop condition completed.
    Stop,
    /// Master finished transmitting a byte.  Carries the
    /// byte that was on the wire so a coupled slave can
    /// decide ACK/NACK.
    TxByte(u8),
    /// Master finished a byte-receive cycle.  The byte
    /// must come from a coupled slave (RxByte data
    /// injection is Phase-3.5+ work; today this variant
    /// is reserved).
    RxByte,
}

#[derive(Clone, Debug, Default)]
pub struct Mssp {
    state: I2cState,
    /// Mirror of the byte the last accepted SSPBUF write
    /// loaded.  Used to roll back the SSPBUF backing memory
    /// on a write-collision: per DS40001303H §17.4.5, "If
    /// the user writes to the SSPBUF when a transmit is
    /// already in progress (i.e., SSPSR is still shifting
    /// out a data byte), then WCOL is set and the contents
    /// of the buffer are unchanged (the write doesn't
    /// occur)."  We approximate "the contents are unchanged"
    /// by remembering the previously-accepted byte and
    /// restoring it on collision.  Defaults to 0 if no
    /// prior write has been accepted (reset state).
    last_accepted_sspbuf_byte: u8,
    /// Most-recently-completed bus-level event; consumed
    /// by `take_last_bus_event` and routed to coupled
    /// slaves.  At most one event accumulates per
    /// `tick_tcy` call because each completion drives the
    /// state machine back to Idle and the surplus-Tcy
    /// drop rule means the next trigger waits on a fresh
    /// SFR write.
    last_bus_event: Option<I2cBusEvent>,
    /// Fault-injection: extra Tcy added to the STOP
    /// completion deadline beyond the normal `scl_period`.
    /// While `stop_busy_count != 0` and a PEN-driven STOP is
    /// scheduled, the state-machine deadline is
    /// `scl_period + stop_busy_cycles` instead of
    /// `scl_period`, simulating a stuck PEN bit (firmware
    /// writes 1 to PEN, MSSP keeps PEN=1 longer than usual
    /// before clearing it via `complete_stop`).  Mirror of
    /// gpsim's `MainChainHarness.set_mssp_stop_fault(
    /// stop_busy_cycles=N)` (chain_gpsim.py:451).  Set to 0
    /// to disable the cycle extension; `clear_mssp_stop_
    /// faults()` zeroes both.
    stop_busy_cycles: u32,
    /// Fault-injection: how many more PEN-driven STOPs to
    /// fault.  Decrements per scheduled STOP while > 0;
    /// -1 means "fault every STOP indefinitely".  When 0
    /// no STOP is faulted regardless of `stop_busy_cycles`.
    /// Mirror of gpsim's `stop_busy_count` knob.  Defaults
    /// to 0 (no fault).
    stop_busy_count: i64,
}

impl Mssp {
    pub fn new(_variant: Variant) -> Self {
        Mssp::default()
    }

    pub fn reset_state(&mut self) {
        self.state = I2cState::Idle;
        self.last_accepted_sspbuf_byte = 0;
        self.last_bus_event = None;
    }

    /// Program the STOP-fault knobs.  While `count != 0` and
    /// the firmware schedules a PEN-driven STOP, the
    /// state-machine deadline is extended by `cycles` Tcy
    /// before `complete_stop` clears PEN.  `count > 0`
    /// decrements per scheduled STOP and stops faulting once
    /// it reaches 0; `count = -1` faults indefinitely.
    /// Mirror of gpsim's
    /// `MainChainHarness.set_mssp_stop_fault(
    /// stop_busy_cycles=N, stop_busy_count=M)`
    /// (chain_gpsim.py:451).
    pub fn set_stop_fault(&mut self, cycles: u32, count: i64) {
        self.stop_busy_cycles = cycles;
        self.stop_busy_count = count;
    }

    /// Clear all MSSP fault-injection knobs.  Mirror of
    /// gpsim's `MainChainHarness.clear_mssp_stop_faults()`
    /// (chain_gpsim.py:468) which zeroes both knobs.
    pub fn clear_stop_faults(&mut self) {
        self.stop_busy_cycles = 0;
        self.stop_busy_count = 0;
    }

    /// Drain the most-recently-completed bus event for the
    /// chain dispatcher to route to coupled slaves.  Returns
    /// `None` if no event has fired since the last call.
    pub fn take_last_bus_event(&mut self) -> Option<I2cBusEvent> {
        self.last_bus_event.take()
    }

    /// Override ACKSTAT in the master core's SFR memory
    /// after `complete_tx_byte` has run.  Called by the
    /// chain dispatcher when a coupled slave decided to ACK
    /// the byte that was just transmitted; the default
    /// `complete_tx_byte` set ACKSTAT=1 (NACK) since there's
    /// no in-peripheral knowledge of bus topology.
    pub fn override_acked(mem: &mut Memory) {
        let con2 = mem.read_raw(crate::memory::Address::from_raw(SSPCON2_ADDR));
        mem.write_raw(
            crate::memory::Address::from_raw(SSPCON2_ADDR),
            con2 & !SSPCON2_ACKSTAT,
        );
    }

    pub fn on_sfr_write(&mut self, addr: u16, value: u8, mem: &mut Memory) {
        match addr {
            SSPCON2_ADDR => self.handle_sspcon2_write(value, mem),
            SSPBUF_ADDR => self.handle_sspbuf_write(value, mem),
            SSPCON1_ADDR | SSPSTAT_ADDR | SSPADD_ADDR | SSPMSK_ADDR => {}
            _ => {}
        }
    }

    pub fn tick_tcy(&mut self, n: u32, mem: &mut Memory) {
        let remaining = match self.state {
            I2cState::Idle => return,
            I2cState::Start(r)
            | I2cState::RepeatedStart(r)
            | I2cState::Stop(r)
            | I2cState::TxByte(r)
            | I2cState::RxByte(r)
            | I2cState::AckPulse(r) => r,
        };
        if n < remaining {
            // Subtract from the current state's countdown.
            self.state = match self.state {
                I2cState::Start(_) => I2cState::Start(remaining - n),
                I2cState::RepeatedStart(_) => I2cState::RepeatedStart(remaining - n),
                I2cState::Stop(_) => I2cState::Stop(remaining - n),
                I2cState::TxByte(_) => I2cState::TxByte(remaining - n),
                I2cState::RxByte(_) => I2cState::RxByte(remaining - n),
                I2cState::AckPulse(_) => I2cState::AckPulse(remaining - n),
                I2cState::Idle => unreachable!(),
            };
            return;
        }
        // Transfer complete this tick.  Surplus Tcy beyond
        // `remaining` are dropped -- the next trigger has to
        // come from a new SFR write.
        match self.state {
            I2cState::Start(_) => self.complete_start(mem),
            I2cState::RepeatedStart(_) => self.complete_repeated_start(mem),
            I2cState::Stop(_) => self.complete_stop(mem),
            I2cState::TxByte(_) => self.complete_tx_byte(mem),
            I2cState::RxByte(_) => self.complete_rx_byte(mem),
            I2cState::AckPulse(_) => self.complete_ack_pulse(mem),
            I2cState::Idle => unreachable!(),
        }
        self.state = I2cState::Idle;
    }

    /// React to a SSPCON2 write.  Each event-trigger bit
    /// schedules its own state ONLY if the module is enabled
    /// AND currently idle.  Per DS §17.4.7:  "lower SSPCON2
    /// event bits may not be set while the I²C module is not
    /// idle".  Concurrent multi-bit writes (e.g. SEN+PEN at
    /// once -- a firmware bug) are ignored beyond the first
    /// bit checked, with priority SEN > RSEN > PEN > RCEN >
    /// ACKEN reflecting the natural transfer-flow order.
    fn handle_sspcon2_write(&mut self, value: u8, mem: &mut Memory) {
        if !is_i2c_master_enabled(mem) {
            return;
        }
        if !matches!(self.state, I2cState::Idle) {
            // Module busy -- silicon ignores any newly-set
            // event-trigger bit.  But the SW write has
            // already landed in memory via apply_sfr_sw_write,
            // so we have to roll back any orphan trigger
            // bits the firmware is trying to set right now.
            // Without this, a "SEN in flight; firmware writes
            // PEN=1" sequence leaves PEN=1 in memory after
            // SEN auto-clears -- causing the firmware's later
            // PEN-clear poll to hang.  Strategy: keep the
            // in-flight trigger bit, clear all others.
            let con2 = mem.read_raw(crate::memory::Address::from_raw(SSPCON2_ADDR));
            let in_flight = current_in_flight_trigger_bit(&self.state);
            let new_con2 = (con2 & !SSPCON2_ALL_TRIGGERS) | in_flight;
            mem.write_raw(crate::memory::Address::from_raw(SSPCON2_ADDR), new_con2);
            return;
        }
        let period = scl_period_tcy(mem);
        // Start: ≈ 1 SCL period for the SDA-fall-while-SCL-
        // high glitch + post-condition idle.  Use the full
        // SCL period as the schedule budget for Phase-2
        // approximation.
        if (value & SSPCON2_SEN) != 0 {
            self.state = I2cState::Start(period);
        } else if (value & SSPCON2_RSEN) != 0 {
            self.state = I2cState::RepeatedStart(period);
        } else if (value & SSPCON2_PEN) != 0 {
            // Fault-injection: extend STOP deadline by
            // `stop_busy_cycles` while `stop_busy_count != 0`.
            // Mirrors gpsim's `set_mssp_stop_fault(
            // stop_busy_cycles=N, stop_busy_count=M)` knob
            // used by V3.1 robustness tests to pin the firmware
            // in i2c_wait_bus_idle while PEN appears stuck.
            let extra = if self.stop_busy_count != 0 {
                if self.stop_busy_count > 0 {
                    self.stop_busy_count -= 1;
                }
                self.stop_busy_cycles
            } else {
                0
            };
            self.state = I2cState::Stop(period.saturating_add(extra));
        } else if (value & SSPCON2_RCEN) != 0 {
            // Master receive: 8 SCL periods of data shift
            // (per DS §17.4.6: "RCEN must be set after each
            // byte received").  The master ACK on the 9th
            // bit is a SEPARATE ACKEN sequence that
            // firmware schedules after RCEN clears -- not
            // part of RCEN's window.
            self.state = I2cState::RxByte(8 * period);
        } else if (value & SSPCON2_ACKEN) != 0 {
            self.state = I2cState::AckPulse(period);
        }
    }

    /// SSPBUF write semantics:
    ///   * If peripheral is enabled AND idle: load byte,
    ///     set BF, schedule TxByte (8 bits + ACK = 9 SCL
    ///     periods).
    ///   * If peripheral is enabled AND busy: silicon sets
    ///     SSPCON1.WCOL (write-collision) and discards the
    ///     write.  BF stays as-is; no TxByte scheduled.
    ///     Per DS40001303H §17.4.7 ("Master mode transmit
    ///     -- write collision").
    ///   * If peripheral is disabled: SSPBUF is just a
    ///     memory latch.  BF asserts (buffer holds the
    ///     byte) -- matches the SSPBUF-as-latch behavior --
    ///     but no TxByte runs.  Phase-2 firmware idiom is
    ///     to enable the peripheral first then write
    ///     SSPBUF, so this branch is mostly defensive.
    fn handle_sspbuf_write(&mut self, written_byte: u8, mem: &mut Memory) {
        if !is_i2c_master_enabled(mem) {
            // Peripheral off; SSPBUF is just memory.  Accept
            // the write; BF mirrors the latch-occupied state.
            self.last_accepted_sspbuf_byte = written_byte;
            let s = mem.read_raw(crate::memory::Address::from_raw(SSPSTAT_ADDR));
            mem.write_raw(
                crate::memory::Address::from_raw(SSPSTAT_ADDR),
                s | SSPSTAT_BF,
            );
            return;
        }
        if !matches!(self.state, I2cState::Idle) {
            // Write-collision: set WCOL, leave BF unchanged,
            // don't schedule, AND roll back the SSPBUF
            // backing memory to the byte that was previously
            // loaded -- per DS §17.4.5, "the contents of the
            // buffer are unchanged (the write doesn't
            // occur)".
            let con1 = mem.read_raw(crate::memory::Address::from_raw(SSPCON1_ADDR));
            mem.write_raw(
                crate::memory::Address::from_raw(SSPCON1_ADDR),
                con1 | SSPCON1_WCOL,
            );
            mem.write_raw(
                crate::memory::Address::from_raw(SSPBUF_ADDR),
                self.last_accepted_sspbuf_byte,
            );
            return;
        }
        // Idle path: accept the write, BF asserts, TxByte
        // scheduled.
        self.last_accepted_sspbuf_byte = written_byte;
        let s = mem.read_raw(crate::memory::Address::from_raw(SSPSTAT_ADDR));
        mem.write_raw(
            crate::memory::Address::from_raw(SSPSTAT_ADDR),
            s | SSPSTAT_BF,
        );
        let period = scl_period_tcy(mem);
        self.state = I2cState::TxByte(9 * period);
    }

    fn complete_start(&mut self, mem: &mut Memory) {
        clear_sspcon2_bit(mem, SSPCON2_SEN);
        assert_sspif(mem);
        self.last_bus_event = Some(I2cBusEvent::Start);
    }

    fn complete_repeated_start(&mut self, mem: &mut Memory) {
        clear_sspcon2_bit(mem, SSPCON2_RSEN);
        assert_sspif(mem);
        self.last_bus_event = Some(I2cBusEvent::RepeatedStart);
    }

    fn complete_stop(&mut self, mem: &mut Memory) {
        clear_sspcon2_bit(mem, SSPCON2_PEN);
        assert_sspif(mem);
        self.last_bus_event = Some(I2cBusEvent::Stop);
    }

    fn complete_tx_byte(&mut self, mem: &mut Memory) {
        // BF clears (shifter consumed the byte).  ACKSTAT
        // defaults to 1 (NACK) -- the chain dispatcher
        // will call `Mssp::override_acked` after routing
        // the event to coupled slaves if any of them ACKed.
        let s = mem.read_raw(crate::memory::Address::from_raw(SSPSTAT_ADDR));
        mem.write_raw(
            crate::memory::Address::from_raw(SSPSTAT_ADDR),
            s & !SSPSTAT_BF,
        );
        let con2 = mem.read_raw(crate::memory::Address::from_raw(SSPCON2_ADDR));
        mem.write_raw(
            crate::memory::Address::from_raw(SSPCON2_ADDR),
            con2 | SSPCON2_ACKSTAT,
        );
        assert_sspif(mem);
        self.last_bus_event = Some(I2cBusEvent::TxByte(self.last_accepted_sspbuf_byte));
    }

    fn complete_rx_byte(&mut self, mem: &mut Memory) {
        // RCEN auto-clears at end of receive.  BF asserts
        // (buffer now holds the received byte; we leave the
        // SSPBUF byte at whatever was previously there since
        // there's no actual bus driving data).
        clear_sspcon2_bit(mem, SSPCON2_RCEN);
        let s = mem.read_raw(crate::memory::Address::from_raw(SSPSTAT_ADDR));
        mem.write_raw(
            crate::memory::Address::from_raw(SSPSTAT_ADDR),
            s | SSPSTAT_BF,
        );
        assert_sspif(mem);
        self.last_bus_event = Some(I2cBusEvent::RxByte);
    }

    fn complete_ack_pulse(&mut self, mem: &mut Memory) {
        clear_sspcon2_bit(mem, SSPCON2_ACKEN);
        assert_sspif(mem);
    }
}

/// Map an in-flight state to the SSPCON2 trigger bit that's
/// associated with it (the bit silicon auto-clears at the
/// end of the sequence).  Returns 0 for in-flight states
/// triggered by something other than SSPCON2 (TxByte is
/// triggered by an SSPBUF write, no SSPCON2 bit involved).
fn current_in_flight_trigger_bit(state: &I2cState) -> u8 {
    match state {
        I2cState::Idle => 0,
        I2cState::Start(_) => SSPCON2_SEN,
        I2cState::RepeatedStart(_) => SSPCON2_RSEN,
        I2cState::Stop(_) => SSPCON2_PEN,
        I2cState::RxByte(_) => SSPCON2_RCEN,
        I2cState::AckPulse(_) => SSPCON2_ACKEN,
        I2cState::TxByte(_) => 0,
    }
}

fn clear_sspcon2_bit(mem: &mut Memory, bit: u8) {
    let con2 = mem.read_raw(crate::memory::Address::from_raw(SSPCON2_ADDR));
    mem.write_raw(
        crate::memory::Address::from_raw(SSPCON2_ADDR),
        con2 & !bit,
    );
}

fn assert_sspif(mem: &mut Memory) {
    let pir1 = mem.read_raw(crate::memory::Address::from_raw(PIR1_ADDR));
    mem.write_raw(
        crate::memory::Address::from_raw(PIR1_ADDR),
        pir1 | PIR1_SSPIF,
    );
}

/// Compute the SCL bit period in Tcy from SSPADD.  Per
/// DS40001303H §17.4.7: `SSPADD = Fcy / FSCL - 1`, so
/// `bit_period_tcy = SSPADD + 1`.  (The `4 × (SSPADD+1)` form
/// floating around earlier in the codebase was a misread of
/// the FOSC-side formula -- in Tcy units the factor is 1.)
/// Clamp to 1 so a 0-divisor doesn't deadlock.
fn scl_period_tcy(mem: &Memory) -> u32 {
    let sspadd = mem.read_raw(crate::memory::Address::from_raw(SSPADD_ADDR)) as u32;
    (sspadd + 1).max(1)
}

fn is_i2c_master_enabled(mem: &Memory) -> bool {
    let con1 = mem.read_raw(crate::memory::Address::from_raw(SSPCON1_ADDR));
    (con1 & SSPCON1_SSPEN) != 0 && (con1 & SSPCON1_SSPM_MASK) == SSPM_I2C_MASTER
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::memory::{Address, Variant};

    fn fresh_mem() -> Memory {
        Memory::new(Variant::Pic18F2455)
    }

    fn enable_i2c_master(mem: &mut Memory, sspadd: u8) {
        mem.write_raw(Address::from_raw(SSPCON1_ADDR), SSPCON1_SSPEN | SSPM_I2C_MASTER);
        mem.write_raw(Address::from_raw(SSPADD_ADDR), sspadd);
    }

    /// SSPADD=0x77 (V3.2 setup) -> bit_period = 0x77+1 = 120
    /// Tcy.  At 4 MIPS Fcy that's 30 µs/bit ≈ 33 kHz.
    #[test]
    fn scl_period_v32_setup() {
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(SSPADD_ADDR), 0x77);
        assert_eq!(scl_period_tcy(&mem), 120);
    }

    #[test]
    fn scl_period_minimum_is_one_tcy_per_bit() {
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(SSPADD_ADDR), 0);
        assert_eq!(scl_period_tcy(&mem), 1);
    }

    #[test]
    fn sen_with_i2c_master_disabled_is_noop() {
        let mut mssp = Mssp::default();
        let mut mem = fresh_mem();
        mssp.on_sfr_write(SSPCON2_ADDR, SSPCON2_SEN, &mut mem);
        assert_eq!(mssp.state, I2cState::Idle);
    }

    #[test]
    fn sen_schedules_start_for_one_scl_period() {
        let mut mssp = Mssp::default();
        let mut mem = fresh_mem();
        enable_i2c_master(&mut mem, 0x77);
        mssp.on_sfr_write(SSPCON2_ADDR, SSPCON2_SEN, &mut mem);
        assert_eq!(mssp.state, I2cState::Start(120));
    }

    #[test]
    fn rsen_schedules_repeated_start() {
        let mut mssp = Mssp::default();
        let mut mem = fresh_mem();
        enable_i2c_master(&mut mem, 0x77);
        mssp.on_sfr_write(SSPCON2_ADDR, SSPCON2_RSEN, &mut mem);
        assert_eq!(mssp.state, I2cState::RepeatedStart(120));
    }

    #[test]
    fn pen_schedules_stop() {
        let mut mssp = Mssp::default();
        let mut mem = fresh_mem();
        enable_i2c_master(&mut mem, 0x77);
        mssp.on_sfr_write(SSPCON2_ADDR, SSPCON2_PEN, &mut mem);
        assert_eq!(mssp.state, I2cState::Stop(120));
    }

    /// Fault-injection: while `set_stop_fault(N, count)`
    /// is active and count != 0, scheduling a PEN-driven
    /// STOP extends the deadline by N Tcy beyond the
    /// normal scl_period.  Mirror of gpsim's
    /// `set_mssp_stop_fault(stop_busy_cycles=N,
    /// stop_busy_count=M)`.
    #[test]
    fn pen_with_stop_fault_extends_deadline() {
        let mut mssp = Mssp::default();
        let mut mem = fresh_mem();
        enable_i2c_master(&mut mem, 0x77);
        mssp.set_stop_fault(5_000, 2);
        // First STOP: faulted, deadline = 120 + 5000.
        mssp.on_sfr_write(SSPCON2_ADDR, SSPCON2_PEN, &mut mem);
        assert_eq!(mssp.state, I2cState::Stop(120 + 5_000));
        assert_eq!(mssp.stop_busy_count, 1);
        // Reset state to allow another schedule, then
        // second STOP: also faulted (count=1 -> 0).
        mssp.state = I2cState::Idle;
        mem.write_raw(crate::memory::Address::from_raw(SSPCON2_ADDR), 0);
        mssp.on_sfr_write(SSPCON2_ADDR, SSPCON2_PEN, &mut mem);
        assert_eq!(mssp.state, I2cState::Stop(120 + 5_000));
        assert_eq!(mssp.stop_busy_count, 0);
        // Third STOP: counter exhausted, no fault.
        mssp.state = I2cState::Idle;
        mem.write_raw(crate::memory::Address::from_raw(SSPCON2_ADDR), 0);
        mssp.on_sfr_write(SSPCON2_ADDR, SSPCON2_PEN, &mut mem);
        assert_eq!(mssp.state, I2cState::Stop(120));
    }

    /// Fault-injection: count = -1 means "fault every STOP
    /// indefinitely"; counter is NOT decremented and stays
    /// at -1.
    #[test]
    fn pen_with_stop_fault_count_negative_one_runs_forever() {
        let mut mssp = Mssp::default();
        let mut mem = fresh_mem();
        enable_i2c_master(&mut mem, 0x77);
        mssp.set_stop_fault(1_000, -1);
        for _ in 0..5 {
            mssp.state = I2cState::Idle;
            mem.write_raw(crate::memory::Address::from_raw(SSPCON2_ADDR), 0);
            mssp.on_sfr_write(SSPCON2_ADDR, SSPCON2_PEN, &mut mem);
            assert_eq!(mssp.state, I2cState::Stop(120 + 1_000));
            assert_eq!(mssp.stop_busy_count, -1);
        }
    }

    /// `clear_stop_faults` zeroes both knobs; subsequent
    /// PEN reverts to the unmodified scl_period schedule.
    #[test]
    fn clear_stop_faults_disables_extension() {
        let mut mssp = Mssp::default();
        let mut mem = fresh_mem();
        enable_i2c_master(&mut mem, 0x77);
        mssp.set_stop_fault(5_000, -1);
        mssp.clear_stop_faults();
        mssp.on_sfr_write(SSPCON2_ADDR, SSPCON2_PEN, &mut mem);
        assert_eq!(mssp.state, I2cState::Stop(120));
    }

    /// RCEN -> 8 SCL periods (8-bit shift; ACK is a
    /// separate ACKEN sequence per DS §17.4.6).
    #[test]
    fn rcen_schedules_rx_byte_8_periods() {
        let mut mssp = Mssp::default();
        let mut mem = fresh_mem();
        enable_i2c_master(&mut mem, 0x77);
        mssp.on_sfr_write(SSPCON2_ADDR, SSPCON2_RCEN, &mut mem);
        assert_eq!(mssp.state, I2cState::RxByte(8 * 120));
    }

    /// SSPBUF write while busy must set WCOL, not change
    /// BF, not schedule a TX, AND roll back the SSPBUF
    /// backing byte to the previously-accepted value (per
    /// DS §17.4.5: "contents of the buffer are unchanged").
    #[test]
    fn sspbuf_write_while_busy_sets_wcol_rolls_back_buffer() {
        let mut mssp = Mssp::default();
        let mut mem = fresh_mem();
        enable_i2c_master(&mut mem, 0x77);
        // First TXBuf write: 0x42, accepted.
        mssp.on_sfr_write(SSPBUF_ADDR, 0x42, &mut mem);
        assert_eq!(mssp.last_accepted_sspbuf_byte, 0x42);
        // Now firmware bug: writes SSPBUF again before TX
        // completes.  apply_sfr_sw_write would have stored
        // 0xAA into SSPBUF backing memory before the hook
        // ran, so simulate that:
        mem.write_raw(Address::from_raw(SSPBUF_ADDR), 0xAA);
        mssp.on_sfr_write(SSPBUF_ADDR, 0xAA, &mut mem);
        let con1 = mem.read_raw(Address::from_raw(SSPCON1_ADDR));
        assert_eq!(
            con1 & SSPCON1_WCOL, SSPCON1_WCOL,
            "WCOL must assert on collision write"
        );
        let buf = mem.read_raw(Address::from_raw(SSPBUF_ADDR));
        assert_eq!(
            buf, 0x42,
            "SSPBUF must roll back to previously-accepted byte (got 0x{buf:02X})"
        );
    }

    /// SSPCON2 write while busy with a different trigger bit
    /// must not leave the orphan bit alive in memory.
    #[test]
    fn sspcon2_busy_write_rolls_back_orphan_trigger_bits() {
        let mut mssp = Mssp::default();
        let mut mem = fresh_mem();
        enable_i2c_master(&mut mem, 0x77);
        mssp.on_sfr_write(SSPCON2_ADDR, SSPCON2_SEN, &mut mem);
        // Firmware bug: writes SSPCON2 = PEN while SEN is in
        // flight.  The pre-mssp-hook write_addr_masked
        // already stored the value; we simulate that:
        mem.write_raw(Address::from_raw(SSPCON2_ADDR), SSPCON2_PEN);
        mssp.on_sfr_write(SSPCON2_ADDR, SSPCON2_PEN, &mut mem);
        let con2 = mem.read_raw(Address::from_raw(SSPCON2_ADDR));
        assert_eq!(
            con2 & SSPCON2_PEN, 0,
            "PEN must be rolled back -- module was busy"
        );
        assert_eq!(
            con2 & SSPCON2_SEN, SSPCON2_SEN,
            "SEN must remain set (the in-flight trigger)"
        );
    }

    #[test]
    fn acken_schedules_master_ack_pulse() {
        let mut mssp = Mssp::default();
        let mut mem = fresh_mem();
        enable_i2c_master(&mut mem, 0x77);
        mssp.on_sfr_write(SSPCON2_ADDR, SSPCON2_ACKEN, &mut mem);
        assert_eq!(mssp.state, I2cState::AckPulse(120));
    }

    /// SSPBUF write while idle and master-enabled: schedule
    /// 9 periods (8-bit shift + ACK), set BF.
    #[test]
    fn sspbuf_write_schedules_tx_byte_and_sets_bf() {
        let mut mssp = Mssp::default();
        let mut mem = fresh_mem();
        enable_i2c_master(&mut mem, 0x77);
        mssp.on_sfr_write(SSPBUF_ADDR, 0x42, &mut mem);
        assert_eq!(mssp.state, I2cState::TxByte(9 * 120));
        assert_eq!(
            mem.read_raw(Address::from_raw(SSPSTAT_ADDR)) & SSPSTAT_BF,
            SSPSTAT_BF,
            "BF must assert on SSPBUF write"
        );
    }

    /// Stop completion clears PEN and asserts SSPIF.
    #[test]
    fn stop_completion_clears_pen_and_sets_sspif() {
        let mut mssp = Mssp::default();
        let mut mem = fresh_mem();
        enable_i2c_master(&mut mem, 0x77);
        mem.write_raw(Address::from_raw(SSPCON2_ADDR), SSPCON2_PEN);
        mssp.on_sfr_write(SSPCON2_ADDR, SSPCON2_PEN, &mut mem);
        mssp.tick_tcy(1000, &mut mem);
        assert_eq!(mssp.state, I2cState::Idle);
        let con2 = mem.read_raw(Address::from_raw(SSPCON2_ADDR));
        assert_eq!(con2 & SSPCON2_PEN, 0);
        let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
        assert_eq!(pir1 & PIR1_SSPIF, PIR1_SSPIF);
    }

    /// TX byte completion clears BF, sets ACKSTAT (NACK in
    /// Phase-2 bus-less model), asserts SSPIF.
    #[test]
    fn tx_byte_completion_sets_ackstat_clears_bf_sets_sspif() {
        let mut mssp = Mssp::default();
        let mut mem = fresh_mem();
        enable_i2c_master(&mut mem, 0x77);
        mssp.on_sfr_write(SSPBUF_ADDR, 0x42, &mut mem);
        // Tick past 9 SCL periods.
        mssp.tick_tcy(9 * 120 + 1, &mut mem);
        assert_eq!(mssp.state, I2cState::Idle);
        let stat = mem.read_raw(Address::from_raw(SSPSTAT_ADDR));
        assert_eq!(stat & SSPSTAT_BF, 0, "BF must clear post-TX");
        let con2 = mem.read_raw(Address::from_raw(SSPCON2_ADDR));
        assert_eq!(
            con2 & SSPCON2_ACKSTAT,
            SSPCON2_ACKSTAT,
            "ACKSTAT must reflect bus-less NACK"
        );
        let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
        assert_eq!(pir1 & PIR1_SSPIF, PIR1_SSPIF);
    }

    /// SSPCON2 write while busy is ignored (datasheet says
    /// lower SSPCON2 event bits may not be set while module
    /// is non-idle).
    #[test]
    fn sspcon2_write_ignored_while_busy() {
        let mut mssp = Mssp::default();
        let mut mem = fresh_mem();
        enable_i2c_master(&mut mem, 0x77);
        mssp.on_sfr_write(SSPCON2_ADDR, SSPCON2_SEN, &mut mem);
        let saved = mssp.state.clone();
        // Try to layer PEN on top while Start is pending.
        // Real silicon ignores; my model also ignores.
        mssp.on_sfr_write(SSPCON2_ADDR, SSPCON2_PEN, &mut mem);
        assert_eq!(mssp.state, saved, "second SSPCON2 trigger must be ignored");
    }

    #[test]
    fn idle_tick_does_nothing() {
        let mut mssp = Mssp::default();
        let mut mem = fresh_mem();
        mssp.tick_tcy(10_000, &mut mem);
        assert_eq!(mssp.state, I2cState::Idle);
    }

    #[test]
    fn reset_state_returns_to_idle() {
        let mut mssp = Mssp::default();
        let mut mem = fresh_mem();
        enable_i2c_master(&mut mem, 0x77);
        mssp.on_sfr_write(SSPCON2_ADDR, SSPCON2_SEN, &mut mem);
        assert!(!matches!(mssp.state, I2cState::Idle));
        mssp.reset_state();
        assert_eq!(mssp.state, I2cState::Idle);
    }
}
