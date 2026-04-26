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
const SSPCON1_SSPEN: u8 = 1 << 5;
const SSPCON1_SSPM_MASK: u8 = 0x0F;
const SSPCON2_SEN: u8 = 1 << 0;
const SSPCON2_RSEN: u8 = 1 << 1;
const SSPCON2_PEN: u8 = 1 << 2;
const PIR1_SSPIF: u8 = 1 << 3;

/// I²C master-mode SSPCON1<3:0> SSPM encoding.  Per DS Tbl
/// 17-1 only `1000` selects "I²C Master mode, clock = Fosc /
/// (4 × (SSPADD + 1))".  Other modes (0110/0111 = 7-bit/
/// 10-bit slave; 1011/1110/1111 = firmware-controlled-master
/// variants) aren't modelled in Phase 2.
const SSPM_I2C_MASTER: u8 = 0b1000;

#[derive(Clone, Debug, PartialEq, Eq)]
enum I2cState {
    /// Bus idle.  No transfer in flight.
    Idle,
    /// `SEN` was set; SCL waveform pending (start condition
    /// will assert in `scl_period_tcy / 2` Tcy).
    StartPending(u32),
    /// Start condition asserted; address byte shifting out.
    /// `bits_remaining` decrements once per scl_period_tcy.
    AddrShifting { bits_remaining: u8, period: u32, tcy_to_next_edge: u32 },
    /// Stop condition pending.
    StopPending(u32),
}

impl Default for I2cState {
    fn default() -> Self {
        I2cState::Idle
    }
}

#[derive(Clone, Debug, Default)]
pub struct Mssp {
    state: I2cState,
}

impl Mssp {
    pub fn new(_variant: Variant) -> Self {
        Mssp::default()
    }

    pub fn reset_state(&mut self) {
        self.state = I2cState::Idle;
    }

    pub fn on_sfr_write(&mut self, addr: u16, value: u8, mem: &mut Memory) {
        match addr {
            SSPCON2_ADDR => self.handle_sspcon2_write(value, mem),
            SSPBUF_ADDR => self.handle_sspbuf_write(mem),
            SSPCON1_ADDR | SSPSTAT_ADDR | SSPADD_ADDR | SSPMSK_ADDR => {}
            _ => {}
        }
    }

    pub fn tick_tcy(&mut self, n: u32, mem: &mut Memory) {
        match self.state {
            I2cState::Idle => {}
            I2cState::StartPending(remaining) => {
                if n >= remaining {
                    // Start condition asserted; transition to
                    // addr-shift phase.  AddrShifting consumes
                    // 8 SCL periods for the 7-bit-addr+R/W byte;
                    // the test scope doesn't actually shift bits
                    // onto a bus, so we just count Tcy and clear
                    // SEN at the end via SSPIF.
                    let period = scl_period_tcy(mem);
                    self.state = I2cState::AddrShifting {
                        bits_remaining: 8,
                        period,
                        tcy_to_next_edge: period,
                    };
                } else {
                    self.state = I2cState::StartPending(remaining - n);
                }
            }
            I2cState::AddrShifting {
                mut bits_remaining,
                period,
                mut tcy_to_next_edge,
            } => {
                let mut budget = n;
                while budget >= tcy_to_next_edge && bits_remaining > 0 {
                    budget -= tcy_to_next_edge;
                    bits_remaining -= 1;
                    tcy_to_next_edge = period;
                }
                if bits_remaining == 0 {
                    // 8-bit address shifted out; clear SEN
                    // (SSPCON2 bit 0) and assert SSPIF.
                    self.complete_addr_phase(mem);
                } else {
                    self.state = I2cState::AddrShifting {
                        bits_remaining,
                        period,
                        tcy_to_next_edge: tcy_to_next_edge - budget,
                    };
                }
            }
            I2cState::StopPending(remaining) => {
                if n >= remaining {
                    self.complete_stop_phase(mem);
                } else {
                    self.state = I2cState::StopPending(remaining - n);
                }
            }
        }
    }

    fn handle_sspcon2_write(&mut self, value: u8, mem: &mut Memory) {
        if !is_i2c_master_enabled(mem) {
            return;
        }
        // SEN: schedule start condition.
        if (value & SSPCON2_SEN) != 0 && matches!(self.state, I2cState::Idle) {
            let period = scl_period_tcy(mem);
            self.state = I2cState::StartPending(period / 2);
        }
        // PEN: schedule stop condition.
        if (value & SSPCON2_PEN) != 0 {
            let period = scl_period_tcy(mem);
            self.state = I2cState::StopPending(period);
        }
        let _ = (SSPCON2_RSEN,); // restart-en unused in Phase 2
    }

    fn handle_sspbuf_write(&mut self, mem: &mut Memory) {
        // Setting SSPBUF marks the buffer full -- BF set,
        // shifter starts on the next SCL edge.  In master
        // mode after SEN, this is the address byte.  In the
        // Phase-2 scope we just set BF; the actual bit-shift
        // is the AddrShifting state's job.
        let s = mem.read_raw(crate::memory::Address::from_raw(SSPSTAT_ADDR));
        mem.write_raw(
            crate::memory::Address::from_raw(SSPSTAT_ADDR),
            s | SSPSTAT_BF,
        );
    }

    fn complete_addr_phase(&mut self, mem: &mut Memory) {
        let con2 = mem.read_raw(crate::memory::Address::from_raw(SSPCON2_ADDR));
        // SEN auto-clears at the end of the start sequence
        // (DS §17.4.7).  We extend that to "auto-clear after
        // address shift" for the Phase-2 simplification.
        mem.write_raw(
            crate::memory::Address::from_raw(SSPCON2_ADDR),
            con2 & !SSPCON2_SEN,
        );
        // BF clears (TX byte moved out of buffer); SSPIF
        // asserts.
        let s = mem.read_raw(crate::memory::Address::from_raw(SSPSTAT_ADDR));
        mem.write_raw(
            crate::memory::Address::from_raw(SSPSTAT_ADDR),
            s & !SSPSTAT_BF,
        );
        let pir1 = mem.read_raw(crate::memory::Address::from_raw(PIR1_ADDR));
        mem.write_raw(
            crate::memory::Address::from_raw(PIR1_ADDR),
            pir1 | PIR1_SSPIF,
        );
        self.state = I2cState::Idle;
    }

    fn complete_stop_phase(&mut self, mem: &mut Memory) {
        let con2 = mem.read_raw(crate::memory::Address::from_raw(SSPCON2_ADDR));
        mem.write_raw(
            crate::memory::Address::from_raw(SSPCON2_ADDR),
            con2 & !SSPCON2_PEN,
        );
        let pir1 = mem.read_raw(crate::memory::Address::from_raw(PIR1_ADDR));
        mem.write_raw(
            crate::memory::Address::from_raw(PIR1_ADDR),
            pir1 | PIR1_SSPIF,
        );
        self.state = I2cState::Idle;
    }
}

/// Compute the SCL bit period in Tcy from SSPADD.  Per
/// DS40001303H Tbl 17-1: `Fbus = Fcy / (4 × (SSPADD + 1))`,
/// so `bit_period_tcy = 4 × (SSPADD + 1)`.  Clamp to 1 so
/// a 0-divisor doesn't deadlock.
fn scl_period_tcy(mem: &Memory) -> u32 {
    let sspadd = mem.read_raw(crate::memory::Address::from_raw(SSPADD_ADDR)) as u32;
    (4 * (sspadd + 1)).max(1)
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

    /// SSPADD=0x77 (V3.2 setup) -> bit_period = 4 × (0x77+1)
    /// = 480 Tcy.  At 4 MIPS Fcy that's 120 µs/bit ≈ 33 kHz.
    #[test]
    fn scl_period_v32_setup() {
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(SSPADD_ADDR), 0x77);
        assert_eq!(scl_period_tcy(&mem), 480);
    }

    #[test]
    fn scl_period_clamps_to_one_on_zero_sspadd() {
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(SSPADD_ADDR), 0);
        // 4 × 1 = 4, not clamped to 1 -- the formula already
        // produces 4 at SSPADD=0.  Clamp is for the 0-divisor
        // pathological case which can't actually occur given
        // the formula.  Sanity check.
        assert_eq!(scl_period_tcy(&mem), 4);
    }

    #[test]
    fn sen_with_i2c_master_disabled_is_noop() {
        let mut mssp = Mssp::default();
        let mut mem = fresh_mem();
        // SSPEN=0; SEN write should not start any sequence.
        mssp.on_sfr_write(SSPCON2_ADDR, SSPCON2_SEN, &mut mem);
        assert_eq!(mssp.state, I2cState::Idle);
    }

    #[test]
    fn sen_starts_state_machine_when_enabled() {
        let mut mssp = Mssp::default();
        let mut mem = fresh_mem();
        enable_i2c_master(&mut mem, 0x77);
        mssp.on_sfr_write(SSPCON2_ADDR, SSPCON2_SEN, &mut mem);
        match mssp.state {
            I2cState::StartPending(remaining) => {
                // 480 Tcy / 2 = 240 Tcy until start asserted.
                assert_eq!(remaining, 240);
            }
            _ => panic!("expected StartPending, got {:?}", mssp.state),
        }
    }

    #[test]
    fn pen_with_i2c_master_enabled_schedules_stop() {
        let mut mssp = Mssp::default();
        let mut mem = fresh_mem();
        enable_i2c_master(&mut mem, 0x77);
        mssp.on_sfr_write(SSPCON2_ADDR, SSPCON2_PEN, &mut mem);
        match mssp.state {
            I2cState::StopPending(remaining) => {
                assert_eq!(remaining, 480);
            }
            _ => panic!("expected StopPending, got {:?}", mssp.state),
        }
    }

    #[test]
    fn stop_completion_clears_pen_and_sets_sspif() {
        let mut mssp = Mssp::default();
        let mut mem = fresh_mem();
        enable_i2c_master(&mut mem, 0x77);
        // Set SSPCON2 with PEN; recorded by handler.
        mem.write_raw(Address::from_raw(SSPCON2_ADDR), SSPCON2_PEN);
        mssp.on_sfr_write(SSPCON2_ADDR, SSPCON2_PEN, &mut mem);
        // Tick past the stop pending window.
        mssp.tick_tcy(1000, &mut mem);
        assert_eq!(mssp.state, I2cState::Idle);
        let con2 = mem.read_raw(Address::from_raw(SSPCON2_ADDR));
        assert_eq!(con2 & SSPCON2_PEN, 0, "PEN must auto-clear post-stop");
        let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
        assert_eq!(pir1 & PIR1_SSPIF, PIR1_SSPIF, "SSPIF must assert post-stop");
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
