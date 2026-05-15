//! Timer0/1/2/3 peripheral models.
//!
//! ## Scope
//!
//! V1.71 CONTROL uses Timer0 for the idle-timer countdown;
//! V3.2 MAIN uses Timer3 for the delayed-switch hold +
//! Layer-5 diag counters (per
//! `docs/V163B_DIAGNOSTICS_MENU_SPEC.md`).  Timer1/Timer2
//! are modeled to the DLCP-observable level required by
//! `docs/SIM_REWRITE_RUST_SPEC.md` §11c FID-09.
//!
//! ## SFR addresses (DS40001303H Tbl 5-1)
//!
//! | Addr  | Reg     | Role                                |
//! |-------|---------|-------------------------------------|
//! | 0xFD7 | TMR0H   | Timer0 high byte (latched on TMR0L read) |
//! | 0xFD6 | TMR0L   | Timer0 low byte                     |
//! | 0xFD5 | T0CON   | TMR0ON, T08BIT, T0CS, T0SE, PSA, T0PS<2:0> |
//! | 0xFCF | TMR1H   | Timer1 high byte / buffer           |
//! | 0xFCE | TMR1L   | Timer1 low byte                     |
//! | 0xFCD | T1CON   | RD16, T1RUN, T1CKPS<1:0>, TMR1CS, TMR1ON |
//! | 0xFCC | TMR2    | Timer2 counter                      |
//! | 0xFCB | PR2     | Timer2 period                       |
//! | 0xFCA | T2CON   | T2OUTPS<3:0>, TMR2ON, T2CKPS<1:0>  |
//! | 0xFB3 | TMR3H   | Timer3 high byte (latched on TMR3L read) |
//! | 0xFB2 | TMR3L   | Timer3 low byte                     |
//! | 0xFB1 | T3CON   | RD16, T3CCP2, T3CKPS<1:0>, T3CCP1, T3SYNC, TMR3CS, TMR3ON |
//!
//! Interrupt flags:
//!
//! - INTCON.TMR0IF (bit 2) -- Timer0 overflow
//! - PIR1.TMR1IF (bit 0) -- Timer1 overflow
//! - PIR1.TMR2IF (bit 1) -- Timer2 period/postscale match
//! - PIR2.TMR3IF (bit 1) -- Timer3 overflow
//!
//! ## Phase-2 timing model
//!
//! Timers run in their internal-clock-source mode with a
//! per-Tcy increment scaled by the prescaler.  External
//! sources are modeled as explicit edge-injection hooks; the
//! pin-network that calls those hooks is FID-14 work.
//!
//! Timer0 prescaler: T0CON.PSA=0 enables the prescaler;
//! T0PS<2:0> selects 1:2..1:256.  At the prescaled rate
//! TMR0 increments by 1 per Tcy / prescaler-divisor.
//!
//! Timer3 prescaler: T3CON.T3CKPS<1:0> selects 1:1..1:8.
//! Timer2 prescaler: T2CON.T2CKPS<1:0> selects 1:1, 1:4,
//! then 1:16 for both `10` and `11`; T2OUTPS selects 1:1
//! through 1:16 interrupt postscaling.
//!
//! ## Read-modify-write semantics
//!
//! TMR0H / TMR1H / TMR3H are latched-buffer registers in
//! 16-bit mode (T08BIT=0 / RD16=1): a read of TMRxL copies
//! the current high byte into a buffer that the next TMRxH
//! read returns; high-byte writes are staged until the low
//! byte write commits the 16-bit reload.

use crate::memory::{Address, Memory, Variant};
use serde::{Deserialize, Serialize};

pub const TMR0H_ADDR: u16 = 0xFD7;
pub const TMR0L_ADDR: u16 = 0xFD6;
pub const T0CON_ADDR: u16 = 0xFD5;
pub const TMR1H_ADDR: u16 = 0xFCF;
pub const TMR1L_ADDR: u16 = 0xFCE;
pub const T1CON_ADDR: u16 = 0xFCD;
pub const TMR2_ADDR: u16 = 0xFCC;
pub const PR2_ADDR: u16 = 0xFCB;
pub const T2CON_ADDR: u16 = 0xFCA;
pub const TMR3H_ADDR: u16 = 0xFB3;
pub const TMR3L_ADDR: u16 = 0xFB2;
pub const T3CON_ADDR: u16 = 0xFB1;
pub const INTCON_ADDR: u16 = 0xFF2;
pub const PIR1_ADDR: u16 = 0xF9E;
pub const PIR2_ADDR: u16 = 0xFA1;

const T0CON_TMR0ON: u8 = 1 << 7;
const T0CON_T08BIT: u8 = 1 << 6;
const T0CON_T0CS: u8 = 1 << 5;
const T0CON_PSA: u8 = 1 << 3;
const T0CON_T0PS_MASK: u8 = 0x07;

const T1CON_RD16: u8 = 1 << 7;
const T1CON_T1CKPS_MASK: u8 = 0x30;
const T1CON_T1CKPS_SHIFT: u32 = 4;
const T1CON_TMR1CS: u8 = 1 << 1;
const T1CON_TMR1ON: u8 = 1 << 0;

const T2CON_T2OUTPS_MASK: u8 = 0x78;
const T2CON_T2OUTPS_SHIFT: u32 = 3;
const T2CON_TMR2ON: u8 = 1 << 2;
const T2CON_T2CKPS_MASK: u8 = 0x03;

const T3CON_RD16: u8 = 1 << 7;
const T3CON_TMR3CS: u8 = 1 << 1;
const T3CON_TMR3ON: u8 = 1 << 0;
const T3CON_T3CKPS_MASK: u8 = 0x30;
const T3CON_T3CKPS_SHIFT: u32 = 4;

const INTCON_TMR0IF: u8 = 1 << 2;
const PIR1_TMR1IF: u8 = 1 << 0;
const PIR1_TMR2IF: u8 = 1 << 1;
const PIR2_TMR3IF: u8 = 1 << 1;

#[derive(Serialize, Deserialize, Clone, Debug, Default)]
pub struct Timers {
    /// Tcy accumulator for Timer0's prescaler.  Increments
    /// once per Tcy when the timer is on; rolls over when
    /// it reaches the prescaler divisor and bumps TMR0.
    timer0_prescaler_tcy: u32,
    /// Tcy accumulator for Timer3's prescaler.
    timer3_prescaler_tcy: u32,
    timer1_prescaler_tcy: u32,
    timer2_prescaler_tcy: u32,
    timer2_postscaler_matches: u8,
    tmr0h_live: u8,
    tmr0h_buffer: u8,
    last_t0con_16bit: bool,
    tmr1h_live: u8,
    tmr1h_buffer: u8,
    last_t1con_rd16: bool,
    /// Live Timer3 high byte counter.  Decoupled from the
    /// SFR byte at `TMR3H_ADDR` because, when RD16=1, the
    /// firmware-visible TMR3H is a buffer (per DS §13.4),
    /// not the actual live counter.  In RD16=0 mode the
    /// two are kept mirrored so firmware reads of TMR3H
    /// return the live value directly.
    tmr3h_live: u8,
    /// Hidden TMR3H write-buffer used when T3CON.RD16=1.
    /// Per DS §13.4 ("16-bit Read/Write Mode Operation"):
    /// when RD16=1, a write to TMR3H stores into this
    /// buffer (does NOT touch the live counter and does
    /// NOT reset the prescaler), and a write to TMR3L
    /// transfers the buffer into the live counter
    /// alongside the new low byte (atomic 16-bit reload).
    /// In RD16=0 (legacy 8-bit-pair) mode the buffer is
    /// unused -- TMR3H writes go directly to the live byte.
    tmr3h_buffer: u8,
    /// Tracks the most recent T3CON.RD16 bit state to
    /// detect 0->1 transitions (when we should seed the
    /// buffer from the live byte so a TMR3L commit without
    /// a prior MOVWF TMR3H stages a no-op).  Steady-state
    /// re-writes of T3CON with RD16 unchanged don't touch
    /// the buffer (a buffer staged via a recent MOVWF TMR3H
    /// must survive a subsequent T3CON rewrite).
    last_t3con_rd16: bool,
}

impl Timers {
    pub fn new(_variant: Variant) -> Self {
        Timers::default()
    }

    /// Pre-SFR-reset cleanup: drops in-flight prescaler
    /// accumulators only.  Called from `apply_reset` BEFORE
    /// the SFR-side reset runs.  Deliberately does NOT
    /// touch `tmr3h_live`, `tmr3h_buffer`, or
    /// `last_t3con_rd16` -- those are authoritatively
    /// re-derived from canonical SFR memory by
    /// `sync_from_memory` for sources that touch the SFR
    /// window (POR/BOR/MCLR/WDT/RESET) and intentionally
    /// preserved across stack-only resets that don't
    /// touch SFRs.
    pub fn reset_state(&mut self) {
        self.timer0_prescaler_tcy = 0;
        self.timer3_prescaler_tcy = 0;
        self.timer1_prescaler_tcy = 0;
        self.timer2_prescaler_tcy = 0;
        self.timer2_postscaler_matches = 0;
    }

    /// Test-only: read the current Timer3 live high byte
    /// shadow.  Public for cross-module reset-path tests
    /// that need to assert the shadow survived a reset
    /// without going through SFR memory (which can hold the
    /// firmware buffer in RD16=1 mode).
    #[doc(hidden)]
    pub fn tmr3h_live_for_test(&self) -> u8 {
        self.tmr3h_live
    }

    /// Post-SFR-reset sync: aligns peripheral internal
    /// shadows with the now-canonical SFR memory.  Handles
    /// the divergent reset semantics (POR/BOR wipe SFRs;
    /// MCLR/WDT/RESET preserve them per Tbl 4-4) without
    /// each peripheral having to know which reset source
    /// fired.  Called from `apply_reset` AFTER all SFR-side
    /// reset passes.
    pub fn sync_from_memory(&mut self, mem: &Memory) {
        // Timer3 live high byte mirrors memory[TMR3H] in the
        // RD16=0 case (and resets to 0 in the RD16=1 POR
        // case where buffer-mode hasn't established a
        // distinct live byte yet).  Reading directly from
        // memory after reset gives the right answer for both
        // POR/BOR (memory wiped to 0) and MCLR/WDT/RESET
        // (memory preserved) branches without per-source
        // logic.
        self.tmr3h_live = mem.read_raw(Address::from_raw(TMR3H_ADDR));
        // Buffer is reset-source-dependent: POR/BOR wipe
        // memory so the natural buffer state is also 0;
        // MCLR/WDT/RESET preserves the firmware-visible
        // TMR3H byte and we re-seed the buffer from it so
        // the first post-reset TMR3L commit doesn't stage
        // garbage.  Mirroring buffer = memory[TMR3H] gives
        // the correct value for both cases.
        self.tmr3h_buffer = mem.read_raw(Address::from_raw(TMR3H_ADDR));
        // Re-derive the RD16-tracking flag from the
        // canonical post-reset T3CON byte so the next T3CON
        // write doesn't misclassify a steady-state mode as a
        // 0->1 transition.
        let t3con = mem.read_raw(Address::from_raw(T3CON_ADDR));
        self.last_t3con_rd16 = (t3con & T3CON_RD16) != 0;

        self.tmr0h_live = mem.read_raw(Address::from_raw(TMR0H_ADDR));
        self.tmr0h_buffer = self.tmr0h_live;
        let t0con = mem.read_raw(Address::from_raw(T0CON_ADDR));
        self.last_t0con_16bit = (t0con & T0CON_T08BIT) == 0;

        self.tmr1h_live = mem.read_raw(Address::from_raw(TMR1H_ADDR));
        self.tmr1h_buffer = self.tmr1h_live;
        let t1con = mem.read_raw(Address::from_raw(T1CON_ADDR));
        self.last_t1con_rd16 = (t1con & T1CON_RD16) != 0;
    }

    pub fn on_sfr_write(&mut self, addr: u16, value: u8, mem: &mut Memory) {
        match addr {
            T0CON_ADDR => {
                let t0con = mem.read_raw(Address::from_raw(T0CON_ADDR));
                let new_16bit = (t0con & T0CON_T08BIT) == 0;
                if new_16bit && !self.last_t0con_16bit {
                    self.tmr0h_buffer = self.tmr0h_live;
                } else if !new_16bit {
                    mem.write_raw(Address::from_raw(TMR0H_ADDR), self.tmr0h_live);
                }
                self.last_t0con_16bit = new_16bit;
                self.timer0_prescaler_tcy = 0;
            }
            T1CON_ADDR => {
                let t1con = mem.read_raw(Address::from_raw(T1CON_ADDR));
                let new_rd16 = (t1con & T1CON_RD16) != 0;
                if new_rd16 && !self.last_t1con_rd16 {
                    self.tmr1h_buffer = self.tmr1h_live;
                } else if !new_rd16 {
                    mem.write_raw(Address::from_raw(TMR1H_ADDR), self.tmr1h_live);
                }
                self.last_t1con_rd16 = new_rd16;
                self.timer1_prescaler_tcy = 0;
            }
            T2CON_ADDR | TMR2_ADDR => {
                self.timer2_prescaler_tcy = 0;
                self.timer2_postscaler_matches = 0;
            }
            T3CON_ADDR => {
                // T3CON write -- handle the post-write
                // RD16 state with one-way sync (live ->
                // memory only, never memory -> live).
                //
                //   * RD16=0 after the write: SFR memory IS
                //     the live byte going forward.  Mirror
                //     `tmr3h_live` into memory so firmware
                //     reads return the live high byte.
                //     Handles RD16 1->0 transition AND the
                //     steady-state-with-RD16=0 case.
                //   * RD16=1 after the write: SFR memory is
                //     the firmware-visible buffer (separate
                //     from the live counter).  Initialize
                //     `tmr3h_buffer` to the current live
                //     byte so a TMR3L commit *without* a
                //     prior MOVWF TMR3H stages a no-op
                //     (commit copies live -> live).  This
                //     handles the RD16 0->1 transition;
                //     in the steady-state-RD16=1 case the
                //     buffer is already initialised and
                //     this re-init to live is harmless
                //     because firmware re-writes TMR3H
                //     between any two T3CON writes if it
                //     cares about the buffer contents.
                let t3con = mem.read_raw(Address::from_raw(T3CON_ADDR));
                let new_rd16 = (t3con & T3CON_RD16) != 0;
                if !new_rd16 {
                    // RD16=0 after the write: SFR memory IS
                    // the live byte going forward.
                    mem.write_raw(Address::from_raw(TMR3H_ADDR), self.tmr3h_live);
                } else if !self.last_t3con_rd16 {
                    // 0->1 transition only: seed the buffer
                    // from the live byte so a subsequent
                    // TMR3L commit without a prior MOVWF
                    // TMR3H stages a no-op (commit copies
                    // live -> live).  Steady-state RD16=1
                    // re-writes (e.g. firmware tweaking the
                    // prescaler) must NOT clobber a staged
                    // buffer between MOVWF TMR3H and the
                    // pending TMR3L commit.
                    self.tmr3h_buffer = self.tmr3h_live;
                }
                self.last_t3con_rd16 = new_rd16;
                self.timer3_prescaler_tcy = 0;
            }
            // TMR0H / TMR0L writes also reset the prescaler
            // per DS §10.2.
            TMR0L_ADDR => {
                let t0con = mem.read_raw(Address::from_raw(T0CON_ADDR));
                if (t0con & T0CON_T08BIT) == 0 {
                    self.tmr0h_live = self.tmr0h_buffer;
                    mem.write_raw(Address::from_raw(TMR0H_ADDR), self.tmr0h_buffer);
                }
                self.timer0_prescaler_tcy = 0;
            }
            TMR0H_ADDR => {
                let t0con = mem.read_raw(Address::from_raw(T0CON_ADDR));
                if (t0con & T0CON_T08BIT) == 0 {
                    self.tmr0h_buffer = value;
                } else {
                    self.tmr0h_live = value;
                    self.timer0_prescaler_tcy = 0;
                }
            }
            TMR1L_ADDR => {
                let t1con = mem.read_raw(Address::from_raw(T1CON_ADDR));
                if (t1con & T1CON_RD16) != 0 {
                    self.tmr1h_live = self.tmr1h_buffer;
                    mem.write_raw(Address::from_raw(TMR1H_ADDR), self.tmr1h_buffer);
                }
                self.timer1_prescaler_tcy = 0;
            }
            TMR1H_ADDR => {
                let t1con = mem.read_raw(Address::from_raw(T1CON_ADDR));
                if (t1con & T1CON_RD16) != 0 {
                    self.tmr1h_buffer = value;
                } else {
                    self.tmr1h_live = value;
                    self.timer1_prescaler_tcy = 0;
                }
            }
            TMR3L_ADDR => {
                // RD16=1: atomic 16-bit reload.  buffer ->
                // live TMR3H AND mirror to SFR memory; the
                // already-landed `value` at TMR3L_ADDR is
                // the new low byte.
                // RD16=0: just a low-byte write; live high
                // byte unchanged; prescaler resets.
                let t3con = mem.read_raw(Address::from_raw(T3CON_ADDR));
                if (t3con & T3CON_RD16) != 0 {
                    self.tmr3h_live = self.tmr3h_buffer;
                    mem.write_raw(Address::from_raw(TMR3H_ADDR), self.tmr3h_buffer);
                }
                self.timer3_prescaler_tcy = 0;
                let _ = value;
            }
            TMR3H_ADDR => {
                let t3con = mem.read_raw(Address::from_raw(T3CON_ADDR));
                if (t3con & T3CON_RD16) != 0 {
                    // Capture the firmware-written byte into
                    // the buffer.  Restore SFR memory so
                    // tick_timer3 doesn't read it (defensive;
                    // tick reads tmr3h_live regardless).
                    // Per DS §13.4 the TMR3H write does NOT
                    // reset the prescaler in RD16=1 mode.
                    self.tmr3h_buffer = value;
                    // SFR memory at TMR3H_ADDR holds whatever
                    // the firmware wrote -- that's what real
                    // silicon returns on read in RD16=1
                    // (unless the firmware first read TMR3L
                    // to latch the live byte; that read-side
                    // latch is a P2.7 deferral).
                } else {
                    // Legacy 8-bit-pair mode: live byte =
                    // memory byte = `value`.  Prescaler
                    // resets.
                    self.tmr3h_live = value;
                    self.timer3_prescaler_tcy = 0;
                }
            }
            _ => {}
        }
    }

    pub fn on_sfr_read(&mut self, addr: u16, mem: &mut Memory) {
        match addr {
            TMR0L_ADDR => {
                let t0con = mem.read_raw(Address::from_raw(T0CON_ADDR));
                if (t0con & T0CON_T08BIT) == 0 {
                    self.tmr0h_buffer = self.tmr0h_live;
                    mem.write_raw(Address::from_raw(TMR0H_ADDR), self.tmr0h_buffer);
                }
            }
            TMR1L_ADDR => {
                let t1con = mem.read_raw(Address::from_raw(T1CON_ADDR));
                if (t1con & T1CON_RD16) != 0 {
                    self.tmr1h_buffer = self.tmr1h_live;
                    mem.write_raw(Address::from_raw(TMR1H_ADDR), self.tmr1h_buffer);
                }
            }
            TMR3L_ADDR => {
                let t3con = mem.read_raw(Address::from_raw(T3CON_ADDR));
                if (t3con & T3CON_RD16) != 0 {
                    mem.write_raw(Address::from_raw(TMR3H_ADDR), self.tmr3h_live);
                }
            }
            _ => {}
        }
    }

    pub fn tick_tcy(&mut self, n: u32, mem: &mut Memory) {
        self.tick_timer0(n, mem);
        self.tick_timer1(n, mem);
        self.tick_timer2(n, mem);
        self.tick_timer3(n, mem);
    }

    pub fn inject_t0cki_rising_edge(&mut self, mem: &mut Memory) {
        let t0con = mem.read_raw(Address::from_raw(T0CON_ADDR));
        if (t0con & T0CON_TMR0ON) != 0 && (t0con & T0CON_T0CS) != 0 {
            self.advance_timer0_increments(1, mem);
        }
    }

    pub fn inject_t1osc_t13cki_rising_edge(&mut self, mem: &mut Memory) {
        let t1con = mem.read_raw(Address::from_raw(T1CON_ADDR));
        if (t1con & T1CON_TMR1ON) != 0 && (t1con & T1CON_TMR1CS) != 0 {
            self.timer1_prescaler_tcy += 1;
            let prescaler = timer1_prescaler_divisor(t1con);
            let increments = self.timer1_prescaler_tcy / prescaler;
            self.timer1_prescaler_tcy %= prescaler;
            if increments > 0 {
                self.advance_timer1_increments(increments, mem);
            }
        }
        let t3con = mem.read_raw(Address::from_raw(T3CON_ADDR));
        if (t3con & T3CON_TMR3ON) != 0 && (t3con & T3CON_TMR3CS) != 0 {
            self.timer3_prescaler_tcy += 1;
            let prescaler = timer3_prescaler_divisor(t3con);
            let increments = self.timer3_prescaler_tcy / prescaler;
            self.timer3_prescaler_tcy %= prescaler;
            if increments > 0 {
                self.advance_timer3_increments(increments, mem);
            }
        }
    }

    pub fn reset_timer1_for_special_event(&mut self, mem: &mut Memory) {
        self.tmr1h_live = 0;
        self.tmr1h_buffer = 0;
        self.timer1_prescaler_tcy = 0;
        mem.write_raw(Address::from_raw(TMR1L_ADDR), 0);
        mem.write_raw(Address::from_raw(TMR1H_ADDR), 0);
    }

    pub fn reset_timer3_for_special_event(&mut self, mem: &mut Memory) {
        self.tmr3h_live = 0;
        self.tmr3h_buffer = 0;
        self.timer3_prescaler_tcy = 0;
        mem.write_raw(Address::from_raw(TMR3L_ADDR), 0);
        mem.write_raw(Address::from_raw(TMR3H_ADDR), 0);
    }

    fn tick_timer0(&mut self, n: u32, mem: &mut Memory) {
        let t0con = mem.read_raw(Address::from_raw(T0CON_ADDR));
        if t0con & T0CON_TMR0ON == 0 {
            return;
        }
        // Internal-clock-source only in Phase 2.  External
        // pin source (T0CS=1) deferred to Phase 3 pin net.
        if t0con & T0CON_T0CS != 0 {
            return;
        }
        let prescaler = timer0_prescaler_divisor(t0con);
        self.timer0_prescaler_tcy += n;
        let increments = self.timer0_prescaler_tcy / prescaler;
        self.timer0_prescaler_tcy %= prescaler;
        if increments == 0 {
            return;
        }
        self.advance_timer0_increments(increments, mem);
    }

    fn advance_timer0_increments(&mut self, increments: u32, mem: &mut Memory) {
        let t0con = mem.read_raw(Address::from_raw(T0CON_ADDR));
        if t0con & T0CON_T08BIT != 0 {
            // 8-bit mode: TMR0L is the counter; TMR0H is
            // not used.  Overflow at 0xFF -> 0x00.
            advance_8bit_counter(mem, TMR0L_ADDR, increments, INTCON_ADDR, INTCON_TMR0IF);
        } else {
            let lo = mem.read_raw(Address::from_raw(TMR0L_ADDR)) as u32;
            let hi = self.tmr0h_live as u32;
            let cur = (hi << 8) | lo;
            let new_total = cur + increments;
            let new_value = (new_total & 0xFFFF) as u16;
            let wraps = new_total >> 16;
            mem.write_raw(Address::from_raw(TMR0L_ADDR), (new_value & 0xFF) as u8);
            self.tmr0h_live = (new_value >> 8) as u8;
            if wraps > 0 {
                let intcon = mem.read_raw(Address::from_raw(INTCON_ADDR));
                mem.write_raw(Address::from_raw(INTCON_ADDR), intcon | INTCON_TMR0IF);
            }
        }
    }

    fn tick_timer1(&mut self, n: u32, mem: &mut Memory) {
        let t1con = mem.read_raw(Address::from_raw(T1CON_ADDR));
        if t1con & T1CON_TMR1ON == 0 {
            return;
        }
        if t1con & T1CON_TMR1CS != 0 {
            return;
        }
        let prescaler = timer1_prescaler_divisor(t1con);
        self.timer1_prescaler_tcy += n;
        let increments = self.timer1_prescaler_tcy / prescaler;
        self.timer1_prescaler_tcy %= prescaler;
        if increments > 0 {
            self.advance_timer1_increments(increments, mem);
        }
    }

    fn advance_timer1_increments(&mut self, increments: u32, mem: &mut Memory) {
        let t1con = mem.read_raw(Address::from_raw(T1CON_ADDR));
        let lo = mem.read_raw(Address::from_raw(TMR1L_ADDR)) as u32;
        let hi = self.tmr1h_live as u32;
        let cur = (hi << 8) | lo;
        let new_total = cur + increments;
        let new_value = (new_total & 0xFFFF) as u16;
        let wraps = new_total >> 16;
        mem.write_raw(Address::from_raw(TMR1L_ADDR), (new_value & 0xFF) as u8);
        self.tmr1h_live = (new_value >> 8) as u8;
        if (t1con & T1CON_RD16) == 0 {
            mem.write_raw(Address::from_raw(TMR1H_ADDR), self.tmr1h_live);
        }
        if wraps > 0 {
            let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
            mem.write_raw(Address::from_raw(PIR1_ADDR), pir1 | PIR1_TMR1IF);
        }
    }

    fn tick_timer2(&mut self, n: u32, mem: &mut Memory) {
        let t2con = mem.read_raw(Address::from_raw(T2CON_ADDR));
        if t2con & T2CON_TMR2ON == 0 {
            return;
        }
        let prescaler = timer2_prescaler_divisor(t2con);
        self.timer2_prescaler_tcy += n;
        let increments = self.timer2_prescaler_tcy / prescaler;
        self.timer2_prescaler_tcy %= prescaler;
        for _ in 0..increments {
            self.advance_timer2_one(mem, t2con);
        }
    }

    fn advance_timer2_one(&mut self, mem: &mut Memory, t2con: u8) {
        let tmr2 = mem.read_raw(Address::from_raw(TMR2_ADDR));
        let pr2 = mem.read_raw(Address::from_raw(PR2_ADDR));
        let next = tmr2.wrapping_add(1);
        if next > pr2 || tmr2 == pr2 {
            mem.write_raw(Address::from_raw(TMR2_ADDR), 0);
            self.timer2_postscaler_matches = self.timer2_postscaler_matches.wrapping_add(1);
            let divisor = timer2_postscaler_divisor(t2con);
            if self.timer2_postscaler_matches >= divisor {
                self.timer2_postscaler_matches = 0;
                let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
                mem.write_raw(Address::from_raw(PIR1_ADDR), pir1 | PIR1_TMR2IF);
            }
        } else {
            mem.write_raw(Address::from_raw(TMR2_ADDR), next);
        }
    }

    fn tick_timer3(&mut self, n: u32, mem: &mut Memory) {
        let t3con = mem.read_raw(Address::from_raw(T3CON_ADDR));
        if t3con & T3CON_TMR3ON == 0 {
            return;
        }
        // Phase-2: internal-clock-source only.
        if t3con & T3CON_TMR3CS != 0 {
            return;
        }
        let prescaler = timer3_prescaler_divisor(t3con);
        self.timer3_prescaler_tcy += n;
        let increments = self.timer3_prescaler_tcy / prescaler;
        self.timer3_prescaler_tcy %= prescaler;
        if increments == 0 {
            return;
        }
        self.advance_timer3_increments(increments, mem);
    }

    fn advance_timer3_increments(&mut self, increments: u32, mem: &mut Memory) {
        let t3con = mem.read_raw(Address::from_raw(T3CON_ADDR));
        // Use the live shadow for the high byte (decoupled
        // from SFR memory in RD16=1 mode -- see field
        // docstring).  Low byte stays in SFR memory directly:
        // RD16 doesn't add any indirection on TMR3L.
        let lo = mem.read_raw(Address::from_raw(TMR3L_ADDR)) as u32;
        let hi = self.tmr3h_live as u32;
        let cur = (hi << 8) | lo;
        let new_total = cur + increments;
        let new_value = (new_total & 0xFFFF) as u16;
        let wraps = new_total >> 16;
        mem.write_raw(Address::from_raw(TMR3L_ADDR), (new_value & 0xFF) as u8);
        let new_high = (new_value >> 8) as u8;
        self.tmr3h_live = new_high;
        // Mirror live high byte to SFR memory only in RD16=0
        // mode (where SFR memory IS the live byte).  In
        // RD16=1 mode SFR memory is the firmware-visible
        // buffer, separate from the live counter.
        if (t3con & T3CON_RD16) == 0 {
            mem.write_raw(Address::from_raw(TMR3H_ADDR), new_high);
        }
        if wraps > 0 {
            let pir = mem.read_raw(Address::from_raw(PIR2_ADDR));
            mem.write_raw(Address::from_raw(PIR2_ADDR), pir | PIR2_TMR3IF);
        }
    }
}

/// Compute Timer0's prescaler divisor in Tcy.  Per DS Tbl
/// 10-1: PSA=1 -> 1:1 (no prescaler); PSA=0 -> 1:2..1:256
/// from T0PS<2:0>.
fn timer0_prescaler_divisor(t0con: u8) -> u32 {
    if t0con & T0CON_PSA != 0 {
        return 1;
    }
    let ps = (t0con & T0CON_T0PS_MASK) as u32;
    1u32 << (ps + 1)
}

fn timer1_prescaler_divisor(t1con: u8) -> u32 {
    let ps = ((t1con & T1CON_T1CKPS_MASK) >> T1CON_T1CKPS_SHIFT) as u32;
    1u32 << ps
}

fn timer2_prescaler_divisor(t2con: u8) -> u32 {
    match t2con & T2CON_T2CKPS_MASK {
        0 => 1,
        1 => 4,
        _ => 16,
    }
}

fn timer2_postscaler_divisor(t2con: u8) -> u8 {
    ((t2con & T2CON_T2OUTPS_MASK) >> T2CON_T2OUTPS_SHIFT) + 1
}

/// Compute Timer3's prescaler divisor in Tcy.  Per DS Tbl
/// 13-1: T3CKPS<1:0> -> 1:1, 1:2, 1:4, 1:8.
fn timer3_prescaler_divisor(t3con: u8) -> u32 {
    let ps = ((t3con & T3CON_T3CKPS_MASK) >> T3CON_T3CKPS_SHIFT) as u32;
    1u32 << ps
}

/// Advance an 8-bit counter at `lo_addr` by `n`, asserting
/// the IRQ flag at `pir_addr`.`pir_bit` on each wrap.
fn advance_8bit_counter(mem: &mut Memory, lo_addr: u16, n: u32, pir_addr: u16, pir_bit: u8) {
    let cur = mem.read_raw(Address::from_raw(lo_addr)) as u32;
    let new_total = cur + n;
    let new_lo = (new_total & 0xFF) as u8;
    let wraps = new_total >> 8;
    mem.write_raw(Address::from_raw(lo_addr), new_lo);
    if wraps > 0 {
        let pir = mem.read_raw(Address::from_raw(pir_addr));
        mem.write_raw(Address::from_raw(pir_addr), pir | pir_bit);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fresh_mem() -> Memory {
        Memory::new(Variant::Pic18F25K20)
    }

    #[test]
    fn timer0_disabled_does_not_count() {
        let mut t = Timers::default();
        let mut mem = fresh_mem();
        // T0CON=0 -> off.  TMR0L poisoned to detect any
        // unexpected writes.
        mem.write_raw(Address::from_raw(TMR0L_ADDR), 0x42);
        t.tick_tcy(1000, &mut mem);
        assert_eq!(mem.read_raw(Address::from_raw(TMR0L_ADDR)), 0x42);
    }

    #[test]
    fn timer0_internal_clock_psa_no_prescaler_8bit() {
        let mut t = Timers::default();
        let mut mem = fresh_mem();
        // TMR0ON | T08BIT | PSA -> 1:1 prescaler, 8-bit.
        mem.write_raw(
            Address::from_raw(T0CON_ADDR),
            T0CON_TMR0ON | T0CON_T08BIT | T0CON_PSA,
        );
        t.tick_tcy(10, &mut mem);
        assert_eq!(mem.read_raw(Address::from_raw(TMR0L_ADDR)), 10);
    }

    #[test]
    fn timer0_8bit_overflow_sets_tmr0if() {
        let mut t = Timers::default();
        let mut mem = fresh_mem();
        mem.write_raw(
            Address::from_raw(T0CON_ADDR),
            T0CON_TMR0ON | T0CON_T08BIT | T0CON_PSA,
        );
        // 256 Tcy of 1:1 prescaler -> exactly one wrap.
        t.tick_tcy(256, &mut mem);
        assert_eq!(mem.read_raw(Address::from_raw(TMR0L_ADDR)), 0);
        let intcon = mem.read_raw(Address::from_raw(INTCON_ADDR));
        assert_eq!(intcon & INTCON_TMR0IF, INTCON_TMR0IF);
    }

    #[test]
    fn timer0_prescaler_1_to_4_takes_4_tcy_per_increment() {
        let mut t = Timers::default();
        let mut mem = fresh_mem();
        // PSA=0, T0PS<2:0>=001 -> 1:4 prescaler.
        mem.write_raw(
            Address::from_raw(T0CON_ADDR),
            T0CON_TMR0ON | T0CON_T08BIT | 0x01,
        );
        t.tick_tcy(8, &mut mem);
        assert_eq!(mem.read_raw(Address::from_raw(TMR0L_ADDR)), 2);
    }

    #[test]
    fn timer0_16bit_increments_pair() {
        let mut t = Timers::default();
        let mut mem = fresh_mem();
        // TMR0ON | (T08BIT=0 -> 16-bit) | PSA.  Prescaler 1:1.
        mem.write_raw(Address::from_raw(T0CON_ADDR), T0CON_TMR0ON | T0CON_PSA);
        // Tick 0x0100 = 256 -> live TMR0H = 0x01, TMR0L = 0x00.
        // In 16-bit mode, reading TMR0L latches live high into TMR0H.
        t.tick_tcy(0x100, &mut mem);
        assert_eq!(mem.read_raw(Address::from_raw(TMR0L_ADDR)), 0);
        t.on_sfr_read(TMR0L_ADDR, &mut mem);
        assert_eq!(mem.read_raw(Address::from_raw(TMR0H_ADDR)), 1);
        let intcon = mem.read_raw(Address::from_raw(INTCON_ADDR));
        assert_eq!(intcon & INTCON_TMR0IF, 0, "16-bit doesn't wrap at 256");
    }

    #[test]
    fn timer3_disabled_does_not_count() {
        let mut t = Timers::default();
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(TMR3L_ADDR), 0x55);
        t.tick_tcy(1000, &mut mem);
        assert_eq!(mem.read_raw(Address::from_raw(TMR3L_ADDR)), 0x55);
    }

    #[test]
    fn timer3_internal_clock_increments_per_tcy() {
        let mut t = Timers::default();
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(T3CON_ADDR), T3CON_TMR3ON);
        t.tick_tcy(5, &mut mem);
        assert_eq!(mem.read_raw(Address::from_raw(TMR3L_ADDR)), 5);
    }

    #[test]
    fn timer3_overflow_sets_tmr3if() {
        let mut t = Timers::default();
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(T3CON_ADDR), T3CON_TMR3ON);
        t.tick_tcy(0x1_0000, &mut mem);
        assert_eq!(mem.read_raw(Address::from_raw(TMR3L_ADDR)), 0);
        assert_eq!(mem.read_raw(Address::from_raw(TMR3H_ADDR)), 0);
        let pir2 = mem.read_raw(Address::from_raw(PIR2_ADDR));
        assert_eq!(pir2 & PIR2_TMR3IF, PIR2_TMR3IF);
    }

    #[test]
    fn timer3_prescaler_1_to_8() {
        let mut t = Timers::default();
        let mut mem = fresh_mem();
        // T3CKPS<1:0> = 11 -> 1:8 prescaler.
        mem.write_raw(
            Address::from_raw(T3CON_ADDR),
            T3CON_TMR3ON | (0b11 << T3CON_T3CKPS_SHIFT),
        );
        t.tick_tcy(16, &mut mem);
        assert_eq!(mem.read_raw(Address::from_raw(TMR3L_ADDR)), 2);
    }

    #[test]
    fn t0con_write_resets_prescaler_accumulator() {
        let mut t = Timers::default();
        let mut mem = fresh_mem();
        // PSA=0, prescaler 1:4, on.
        mem.write_raw(
            Address::from_raw(T0CON_ADDR),
            T0CON_TMR0ON | T0CON_T08BIT | 0x01,
        );
        t.tick_tcy(2, &mut mem); // accumulator now 2/4
        // Firmware writes T0CON; accumulator must reset.
        t.on_sfr_write(T0CON_ADDR, 0xC9, &mut mem);
        assert_eq!(t.timer0_prescaler_tcy, 0);
    }

    /// reset_state clears prescaler accumulators only.
    /// tmr3h_live / tmr3h_buffer / last_t3con_rd16 are
    /// intentionally NOT touched -- sync_from_memory
    /// repairs them (for SFR-touching resets) or they're
    /// preserved (for stack-only resets that don't touch
    /// SFRs).
    #[test]
    fn reset_state_clears_prescaler_accumulators_only() {
        let mut t = Timers::default();
        t.timer0_prescaler_tcy = 7;
        t.timer3_prescaler_tcy = 3;
        t.last_t3con_rd16 = true;
        t.tmr3h_buffer = 0xAB;
        t.tmr3h_live = 0xCD;
        t.reset_state();
        assert_eq!(t.timer0_prescaler_tcy, 0);
        assert_eq!(t.timer3_prescaler_tcy, 0);
        // last_t3con_rd16, tmr3h_buffer, tmr3h_live all
        // preserved across reset_state.
        assert!(t.last_t3con_rd16);
        assert_eq!(t.tmr3h_buffer, 0xAB);
        assert_eq!(t.tmr3h_live, 0xCD);
    }

    /// RD16 mode: firmware writes TMR3H first (lands in
    /// hidden buffer; live TMR3H untouched, prescaler not
    /// reset), then TMR3L (atomic transfer of buffer ->
    /// live TMR3H AND new TMR3L).  Critical correctness:
    /// during the window between TMR3H write and TMR3L
    /// commit, tick_timer3 MUST NOT advance the counter
    /// using the firmware-buffered byte -- it must use
    /// the live shadow.
    #[test]
    fn timer3_rd16_atomic_reload_via_buffer() {
        let mut t = Timers::default();
        let mut mem = fresh_mem();
        // Enable Timer3 with RD16, internal clock, 1:1
        // prescaler.  T3CON write syncs tmr3h_live from
        // memory (= 0 from POR).
        mem.write_raw(Address::from_raw(T3CON_ADDR), T3CON_TMR3ON | T3CON_RD16);
        t.on_sfr_write(T3CON_ADDR, T3CON_TMR3ON | T3CON_RD16, &mut mem);
        // Tick a bit so the live counter is non-zero (50,0).
        t.tick_tcy(50, &mut mem);
        assert_eq!(mem.read_raw(Address::from_raw(TMR3L_ADDR)), 50);
        assert_eq!(t.tmr3h_live, 0);
        // RD16=1 -> SFR memory at TMR3H mirrors live in
        // current model since no TMR3H write has staged a
        // buffer yet.  Memory should still reflect 0.
        assert_eq!(mem.read_raw(Address::from_raw(TMR3H_ADDR)), 0);

        // Firmware: MOVWF TMR3H with W=0xAB.  Simulate the
        // post-mask SW write that already landed in memory:
        mem.write_raw(Address::from_raw(TMR3H_ADDR), 0xAB);
        t.on_sfr_write(TMR3H_ADDR, 0xAB, &mut mem);
        // RD16 buffer captured; live shadow untouched.
        assert_eq!(t.tmr3h_buffer, 0xAB);
        assert_eq!(
            t.tmr3h_live, 0,
            "tmr3h_live must NOT change on RD16=1 TMR3H write"
        );

        // Tick more; the counter MUST advance from its live
        // value (50, live_high=0), not from the buffered
        // firmware-written byte (50, 0xAB).  After 5 more
        // Tcy: counter = (0,55).  If the implementation
        // were buggy and used SFR memory directly, the
        // counter would be (0xAB, 55) and tmr3h_live would
        // be 0xAB.
        t.tick_tcy(5, &mut mem);
        assert_eq!(mem.read_raw(Address::from_raw(TMR3L_ADDR)), 55);
        assert_eq!(
            t.tmr3h_live, 0,
            "live high byte must remain 0 -- RD16 buffer must not pollute live counter"
        );

        // Firmware: MOVWF TMR3L with W=0x12.  Atomic commit.
        mem.write_raw(Address::from_raw(TMR3L_ADDR), 0x12);
        t.on_sfr_write(TMR3L_ADDR, 0x12, &mut mem);
        assert_eq!(mem.read_raw(Address::from_raw(TMR3L_ADDR)), 0x12);
        assert_eq!(mem.read_raw(Address::from_raw(TMR3H_ADDR)), 0xAB);
        assert_eq!(t.tmr3h_live, 0xAB);
        assert_eq!(t.timer3_prescaler_tcy, 0);
    }

    /// Regression: a second T3CON write while RD16=1 (e.g.
    /// firmware changes prescaler mid-flight without
    /// touching RD16) must NOT pollute tmr3h_live with the
    /// firmware-buffered byte sitting in memory[TMR3H].
    #[test]
    fn timer3_t3con_rewrite_with_rd16_active_does_not_corrupt_live() {
        let mut t = Timers::default();
        let mut mem = fresh_mem();
        // Enable Timer3 with RD16, 1:1 prescaler.
        mem.write_raw(Address::from_raw(T3CON_ADDR), T3CON_TMR3ON | T3CON_RD16);
        t.on_sfr_write(T3CON_ADDR, T3CON_TMR3ON | T3CON_RD16, &mut mem);
        // Tick to a known live state (high=0x05, low=0x00).
        t.tick_tcy(0x500, &mut mem);
        assert_eq!(t.tmr3h_live, 0x05);
        // Firmware stages a buffered byte: MOVWF TMR3H = 0x99.
        mem.write_raw(Address::from_raw(TMR3H_ADDR), 0x99);
        t.on_sfr_write(TMR3H_ADDR, 0x99, &mut mem);
        assert_eq!(t.tmr3h_buffer, 0x99);
        assert_eq!(t.tmr3h_live, 0x05, "live unchanged by RD16=1 TMR3H write");
        // Now firmware re-writes T3CON to change prescaler
        // (still RD16=1).  tmr3h_live MUST NOT be clobbered
        // by memory[TMR3H] = 0x99 (the staged buffer).
        let t3con_new = T3CON_TMR3ON | T3CON_RD16 | (0b01 << T3CON_T3CKPS_SHIFT);
        mem.write_raw(Address::from_raw(T3CON_ADDR), t3con_new);
        t.on_sfr_write(T3CON_ADDR, t3con_new, &mut mem);
        assert_eq!(
            t.tmr3h_live, 0x05,
            "T3CON rewrite with RD16=1 must not pollute live shadow with buffer"
        );
        assert_eq!(t.tmr3h_buffer, 0x99, "buffer survives T3CON rewrite");
    }

    /// RD16 1->0 transition: live shadow must surface into
    /// SFR memory so firmware reading TMR3H sees the live
    /// counter (not the stale buffer).
    #[test]
    fn timer3_rd16_high_to_low_transition_surfaces_live_to_memory() {
        let mut t = Timers::default();
        let mut mem = fresh_mem();
        // Start RD16=1.
        mem.write_raw(Address::from_raw(T3CON_ADDR), T3CON_TMR3ON | T3CON_RD16);
        t.on_sfr_write(T3CON_ADDR, T3CON_TMR3ON | T3CON_RD16, &mut mem);
        t.tick_tcy(0x300, &mut mem);
        assert_eq!(t.tmr3h_live, 3);
        // Stage a buffered byte to make the SFR memory
        // diverge from live.
        mem.write_raw(Address::from_raw(TMR3H_ADDR), 0xCC);
        t.on_sfr_write(TMR3H_ADDR, 0xCC, &mut mem);
        // Firmware switches to RD16=0.
        let t3con_new = T3CON_TMR3ON;
        mem.write_raw(Address::from_raw(T3CON_ADDR), t3con_new);
        t.on_sfr_write(T3CON_ADDR, t3con_new, &mut mem);
        // SFR memory now reflects live (0x03), not the
        // stale buffer (0xCC).
        assert_eq!(
            mem.read_raw(Address::from_raw(TMR3H_ADDR)),
            3,
            "RD16 1->0 must surface live into SFR memory"
        );
    }

    /// RD16 0->1 transition seeds the buffer from the
    /// current live byte, so a TMR3L commit without a prior
    /// MOVWF TMR3H stages a no-op (live -> live).
    #[test]
    fn timer3_rd16_zero_to_one_transition_seeds_buffer_from_live() {
        let mut t = Timers::default();
        let mut mem = fresh_mem();
        // Start RD16=0; tick to a known live byte.
        mem.write_raw(Address::from_raw(T3CON_ADDR), T3CON_TMR3ON);
        t.on_sfr_write(T3CON_ADDR, T3CON_TMR3ON, &mut mem);
        t.tick_tcy(0x500, &mut mem);
        assert_eq!(t.tmr3h_live, 0x05);
        // Firmware enables RD16 (steady state otherwise).
        let t3con_new = T3CON_TMR3ON | T3CON_RD16;
        mem.write_raw(Address::from_raw(T3CON_ADDR), t3con_new);
        t.on_sfr_write(T3CON_ADDR, t3con_new, &mut mem);
        // Buffer seeded from live (= 0x05), not stale 0.
        assert_eq!(
            t.tmr3h_buffer, 0x05,
            "0->1 transition must seed buffer from live"
        );
        // Firmware writes TMR3L without staging TMR3H.
        // Commit: buffer (0x05) -> live; no change.
        mem.write_raw(Address::from_raw(TMR3L_ADDR), 0x10);
        t.on_sfr_write(TMR3L_ADDR, 0x10, &mut mem);
        assert_eq!(t.tmr3h_live, 0x05, "no-op commit preserves live high");
    }

    /// RD16=0 (legacy 8-bit-pair mode): TMR3H writes go
    /// directly to the live byte AND reset the prescaler.
    #[test]
    fn timer3_rd16_off_tmr3h_write_resets_prescaler() {
        let mut t = Timers::default();
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(T3CON_ADDR), T3CON_TMR3ON);
        t.tick_tcy(0, &mut mem); // accumulator stays 0
        t.timer3_prescaler_tcy = 5;
        t.on_sfr_write(TMR3H_ADDR, 0xCD, &mut mem);
        assert_eq!(t.timer3_prescaler_tcy, 0);
    }
}
