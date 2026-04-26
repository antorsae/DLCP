//! Timer0 + Timer3 peripheral models — Phase-2 minimum.
//!
//! ## Scope
//!
//! Only Timer0 and Timer3 are wired here.  V1.71 CONTROL
//! uses Timer0 for the idle-timer countdown; V3.2 MAIN
//! uses Timer3 for the delayed-switch hold + Layer-5
//! diag counters (per
//! `docs/V163B_DIAGNOSTICS_MENU_SPEC.md`).  Timer1 / Timer2
//! exist on both chips but neither firmware family
//! exercises them in Phase-2 boot scope (Timer2 is mainly a
//! PWM period source for the ECCP1 module which we don't
//! model in Phase 2).
//!
//! ## SFR addresses (DS40001303H Tbl 5-1)
//!
//! | Addr  | Reg     | Role                                |
//! |-------|---------|-------------------------------------|
//! | 0xFD7 | TMR0H   | Timer0 high byte (latched on TMR0L read) |
//! | 0xFD6 | TMR0L   | Timer0 low byte                     |
//! | 0xFD5 | T0CON   | TMR0ON, T08BIT, T0CS, T0SE, PSA, T0PS<2:0> |
//! | 0xFB3 | TMR3H   | Timer3 high byte (latched on TMR3L read) |
//! | 0xFB2 | TMR3L   | Timer3 low byte                     |
//! | 0xFB1 | T3CON   | RD16, T3CCP2, T3CKPS<1:0>, T3CCP1, T3SYNC, TMR3CS, TMR3ON |
//!
//! Interrupt flags:
//!
//! - INTCON.TMR0IF (bit 2) -- Timer0 overflow
//! - PIR2.TMR3IF (bit 1) -- Timer3 overflow
//!
//! ## Phase-2 timing model
//!
//! Both timers run in their internal-clock-source mode
//! (T0CS=0 for Timer0; TMR3CS=0 for Timer3) with a
//! per-Tcy increment scaled by the prescaler.  External-
//! pin sources (T0CKI, T1OSC) are Phase-3 pin-network
//! work.
//!
//! Timer0 prescaler: T0CON.PSA=0 enables the prescaler;
//! T0PS<2:0> selects 1:2..1:256.  At the prescaled rate
//! TMR0 increments by 1 per Tcy / prescaler-divisor.
//!
//! Timer3 prescaler: T3CON.T3CKPS<1:0> selects 1:1..1:8.
//!
//! ## Read-modify-write semantics
//!
//! TMR0H / TMR3H are latched-buffer registers in 16-bit
//! mode (T08BIT=0 / RD16=1): a read of TMR0L copies the
//! current high byte into a hidden buffer that the next
//! TMR0H read returns.  The Phase-2 model defers this to
//! P2.7 (when a real test exercises 16-bit Timer reads);
//! for now both halves are independent SFR bytes.

use crate::memory::{Address, Memory, Variant};

pub const TMR0H_ADDR: u16 = 0xFD7;
pub const TMR0L_ADDR: u16 = 0xFD6;
pub const T0CON_ADDR: u16 = 0xFD5;
pub const TMR3H_ADDR: u16 = 0xFB3;
pub const TMR3L_ADDR: u16 = 0xFB2;
pub const T3CON_ADDR: u16 = 0xFB1;
pub const INTCON_ADDR: u16 = 0xFF2;
pub const PIR2_ADDR: u16 = 0xFA1;

const T0CON_TMR0ON: u8 = 1 << 7;
const T0CON_T08BIT: u8 = 1 << 6;
const T0CON_T0CS: u8 = 1 << 5;
const T0CON_PSA: u8 = 1 << 3;
const T0CON_T0PS_MASK: u8 = 0x07;

const T3CON_RD16: u8 = 1 << 7;
const T3CON_TMR3CS: u8 = 1 << 1;
const T3CON_TMR3ON: u8 = 1 << 0;
const T3CON_T3CKPS_MASK: u8 = 0x30;
const T3CON_T3CKPS_SHIFT: u32 = 4;

const INTCON_TMR0IF: u8 = 1 << 2;
const PIR2_TMR3IF: u8 = 1 << 1;

#[derive(Clone, Debug, Default)]
pub struct Timers {
    /// Tcy accumulator for Timer0's prescaler.  Increments
    /// once per Tcy when the timer is on; rolls over when
    /// it reaches the prescaler divisor and bumps TMR0.
    timer0_prescaler_tcy: u32,
    /// Tcy accumulator for Timer3's prescaler.
    timer3_prescaler_tcy: u32,
    /// Hidden TMR3H buffer used when T3CON.RD16=1.  Per DS
    /// §13.4 ("16-bit Read/Write Mode Operation"): when
    /// RD16=1, a read of TMR3L latches the *current* upper
    /// byte into this buffer (firmware then reads TMR3H to
    /// retrieve the latched value), and a write to TMR3L
    /// transfers the buffer into the actual high byte
    /// alongside the new low byte (atomic 16-bit reload).
    /// Writes to TMR3H land in this buffer ONLY -- they do
    /// not touch the live counter and do NOT reset the
    /// prescaler.  Phase-2 Timer3 always treats the
    /// "actual" high byte as the live SFR at TMR3H_ADDR;
    /// when RD16=0 (the legacy 8-bit-pair model), the
    /// buffer is unused.
    tmr3h_buffer: u8,
}

impl Timers {
    pub fn new(_variant: Variant) -> Self {
        Timers::default()
    }

    pub fn reset_state(&mut self) {
        self.timer0_prescaler_tcy = 0;
        self.timer3_prescaler_tcy = 0;
        self.tmr3h_buffer = 0;
    }

    pub fn on_sfr_write(&mut self, addr: u16, value: u8, mem: &mut Memory) {
        match addr {
            // T0CON / T3CON writes change prescaler / enable
            // state; clear our internal Tcy accumulator so
            // the new prescaler period starts fresh.  Real
            // silicon also resets the prescaler on T0CON
            // writes (DS §10.2 "Timer0 Prescaler").
            T0CON_ADDR => self.timer0_prescaler_tcy = 0,
            T3CON_ADDR => self.timer3_prescaler_tcy = 0,
            // TMR0H / TMR0L writes also reset the prescaler
            // per DS §10.2 ("any write to TMR0L resets the
            // prescaler").
            TMR0L_ADDR | TMR0H_ADDR => self.timer0_prescaler_tcy = 0,
            TMR3L_ADDR => {
                // Timer3 RD16 mode: the firmware-visible
                // sequence is "MOVWF TMR3H; MOVWF TMR3L".
                // The TMR3H write was captured in
                // `tmr3h_buffer` (handled below).  This
                // TMR3L write atomically transfers buffer ->
                // live TMR3H byte AND lands `value` as the
                // new TMR3L.  apply_sfr_sw_write already
                // wrote `value` to TMR3L_ADDR, so we just
                // need to overwrite TMR3H with the buffered
                // byte.  Always clears the prescaler per
                // DS §13.4.
                let t3con = mem.read_raw(Address::from_raw(T3CON_ADDR));
                if (t3con & T3CON_RD16) != 0 {
                    mem.write_raw(
                        Address::from_raw(TMR3H_ADDR),
                        self.tmr3h_buffer,
                    );
                }
                self.timer3_prescaler_tcy = 0;
                let _ = value;
            }
            TMR3H_ADDR => {
                // RD16=1: the TMR3H write is supposed to land
                // in a hidden buffer, NOT the live counter.
                // apply_sfr_sw_write has already stored
                // `value` at TMR3H_ADDR -- we have to
                // restore the previous live value (we don't
                // know it without saving across writes;
                // simplest: read the *next* TMR3L write to
                // commit, and meanwhile preserve the live
                // byte unchanged).  Simpler still: capture
                // `value` into the buffer here, then on the
                // next TMR3L write commit it.  The live
                // TMR3H byte is overwritten in memory between
                // here and the TMR3L write, but firmware
                // reads of TMR3H during that window already
                // get unspecified silicon behaviour, so the
                // memory transient is acceptable.
                //
                // RD16=0: legacy 8-bit-pair mode -- TMR3H is
                // a real byte; the write goes through.  No
                // buffer indirection.  Reset the prescaler
                // (preserves the prior LOW finding semantic).
                let t3con = mem.read_raw(Address::from_raw(T3CON_ADDR));
                if (t3con & T3CON_RD16) != 0 {
                    self.tmr3h_buffer = value;
                    // NOTE: per DS §13.4, TMR3H writes in
                    // RD16=1 do NOT reset the prescaler.
                } else {
                    self.timer3_prescaler_tcy = 0;
                }
            }
            _ => {}
        }
    }

    pub fn tick_tcy(&mut self, n: u32, mem: &mut Memory) {
        self.tick_timer0(n, mem);
        self.tick_timer3(n, mem);
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
        if t0con & T0CON_T08BIT != 0 {
            // 8-bit mode: TMR0L is the counter; TMR0H is
            // not used.  Overflow at 0xFF -> 0x00.
            advance_8bit_counter(
                mem,
                TMR0L_ADDR,
                increments,
                INTCON_ADDR,
                INTCON_TMR0IF,
            );
        } else {
            // 16-bit mode: TMR0H:TMR0L is the counter.
            advance_16bit_counter(
                mem,
                TMR0L_ADDR,
                TMR0H_ADDR,
                increments,
                INTCON_ADDR,
                INTCON_TMR0IF,
            );
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
        // Timer3 is always 16-bit on the silicon side (RD16
        // only affects how SW reads/writes the high byte;
        // the underlying counter is 16-bit either way per
        // DS §13).  RD16 is consumed by on_sfr_write to
        // route TMR3H writes through the hidden buffer.
        advance_16bit_counter(
            mem,
            TMR3L_ADDR,
            TMR3H_ADDR,
            increments,
            PIR2_ADDR,
            PIR2_TMR3IF,
        );
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

/// Compute Timer3's prescaler divisor in Tcy.  Per DS Tbl
/// 13-1: T3CKPS<1:0> -> 1:1, 1:2, 1:4, 1:8.
fn timer3_prescaler_divisor(t3con: u8) -> u32 {
    let ps = ((t3con & T3CON_T3CKPS_MASK) >> T3CON_T3CKPS_SHIFT) as u32;
    1u32 << ps
}

/// Advance an 8-bit counter at `lo_addr` by `n`, asserting
/// the IRQ flag at `pir_addr`.`pir_bit` on each wrap.
fn advance_8bit_counter(
    mem: &mut Memory,
    lo_addr: u16,
    n: u32,
    pir_addr: u16,
    pir_bit: u8,
) {
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

/// Advance a 16-bit counter at (`hi_addr`<<8|`lo_addr`) by
/// `n`, asserting the IRQ flag at `pir_addr`.`pir_bit` on
/// each wrap from 0xFFFF -> 0x0000.
fn advance_16bit_counter(
    mem: &mut Memory,
    lo_addr: u16,
    hi_addr: u16,
    n: u32,
    pir_addr: u16,
    pir_bit: u8,
) {
    let lo = mem.read_raw(Address::from_raw(lo_addr)) as u32;
    let hi = mem.read_raw(Address::from_raw(hi_addr)) as u32;
    let cur = (hi << 8) | lo;
    let new_total = cur + n;
    let new_value = (new_total & 0xFFFF) as u16;
    let wraps = new_total >> 16;
    mem.write_raw(Address::from_raw(lo_addr), (new_value & 0xFF) as u8);
    mem.write_raw(Address::from_raw(hi_addr), (new_value >> 8) as u8);
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
        mem.write_raw(
            Address::from_raw(T0CON_ADDR),
            T0CON_TMR0ON | T0CON_PSA,
        );
        // Tick 0x0100 = 256 -> TMR0H = 0x01, TMR0L = 0x00.
        t.tick_tcy(0x100, &mut mem);
        assert_eq!(mem.read_raw(Address::from_raw(TMR0L_ADDR)), 0);
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

    #[test]
    fn reset_state_clears_accumulators() {
        let mut t = Timers::default();
        t.timer0_prescaler_tcy = 7;
        t.timer3_prescaler_tcy = 3;
        t.tmr3h_buffer = 0xAB;
        t.reset_state();
        assert_eq!(t.timer0_prescaler_tcy, 0);
        assert_eq!(t.timer3_prescaler_tcy, 0);
        assert_eq!(t.tmr3h_buffer, 0);
    }

    /// RD16 mode: firmware writes TMR3H first (lands in
    /// hidden buffer; live TMR3H untouched, prescaler not
    /// reset), then TMR3L (atomic transfer of buffer ->
    /// live TMR3H AND new TMR3L).
    #[test]
    fn timer3_rd16_atomic_reload_via_buffer() {
        let mut t = Timers::default();
        let mut mem = fresh_mem();
        // Enable Timer3 with RD16, internal clock, 1:1
        // prescaler.
        mem.write_raw(Address::from_raw(T3CON_ADDR), T3CON_TMR3ON | T3CON_RD16);
        // Tick a bit so the counter is non-zero.
        t.tick_tcy(50, &mut mem);
        let pre_tmr3l = mem.read_raw(Address::from_raw(TMR3L_ADDR));
        assert_eq!(pre_tmr3l, 50);
        let pre_tmr3h = mem.read_raw(Address::from_raw(TMR3H_ADDR));
        assert_eq!(pre_tmr3h, 0);

        // Firmware: MOVWF TMR3H with W=0xAB.  Simulate the
        // post-mask write that already landed:
        mem.write_raw(Address::from_raw(TMR3H_ADDR), 0xAB);
        t.on_sfr_write(TMR3H_ADDR, 0xAB, &mut mem);
        // RD16 buffer captured.
        assert_eq!(t.tmr3h_buffer, 0xAB);
        // Prescaler accumulator NOT reset by TMR3H write per
        // DS §13.4.  The pre-tick consumed 50 Tcy out of a
        // 1:1 prescaler -- accumulator should still be 0
        // because every 1 Tcy increments the counter
        // directly.  More important: a TMR3H write must NOT
        // touch the live counter.  Tick another 5 Tcy and
        // verify the counter advances normally from where
        // it was.
        t.tick_tcy(5, &mut mem);
        let mid_tmr3l = mem.read_raw(Address::from_raw(TMR3L_ADDR));
        assert_eq!(
            mid_tmr3l, 55,
            "TMR3L must keep counting from pre-write value, not be reloaded"
        );

        // Firmware: MOVWF TMR3L with W=0x12.
        mem.write_raw(Address::from_raw(TMR3L_ADDR), 0x12);
        t.on_sfr_write(TMR3L_ADDR, 0x12, &mut mem);
        // After TMR3L write: TMR3L = 0x12 (set by SW write),
        // TMR3H = 0xAB (atomically transferred from buffer).
        // Prescaler reset.
        assert_eq!(mem.read_raw(Address::from_raw(TMR3L_ADDR)), 0x12);
        assert_eq!(mem.read_raw(Address::from_raw(TMR3H_ADDR)), 0xAB);
        assert_eq!(t.timer3_prescaler_tcy, 0);
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
