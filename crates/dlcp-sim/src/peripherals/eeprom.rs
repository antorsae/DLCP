//! EEPROM peripheral — Phase-2 minimum-viable.
//!
//! ## Scope
//!
//! 256 bytes of internal data EEPROM, accessed through the
//! standard PIC18 EEPGD-driven path (DS40001303H §7,
//! DS39632E §7).  Models:
//!
//! - 256-byte backing storage (variant-agnostic for Phase-2;
//!   both K20 and 2455 have 256 B at the address space the
//!   datasheet documents).
//! - EECON1 / EECON2 / EEADR / EEDATA SFRs (PIC18F26K20-
//!   only EEADRH not modelled in Phase 2; the 25K20 has
//!   only 256 bytes so the high byte is unused).
//! - The full unlock sequence: a write is only committed if
//!   firmware has just written 0x55 then 0xAA to EECON2
//!   followed by a single instruction setting EECON1.WR=1.
//!   Any intervening SFR write to EECON2 resets the
//!   sequence (matches silicon's "WR Sequence" behaviour
//!   per DS §7.4).
//! - Read path: setting EECON1.RD=1 with EECON1.EEPGD=0
//!   loads EEDATA from the EEPROM byte at EEADR.  RD
//!   self-clears at the end of the same Tcy.
//! - Write path: after a valid unlock + WR=1 with EEPGD=0
//!   AND EECON1.WREN=1, schedule a fixed post-write timer.
//!   On completion: store EEDATA to EEPROM[EEADR], clear
//!   EECON1.WR, assert PIR2.EEIF.
//!
//! ## Deliberate fidelity exceedance over gpsim
//!
//! gpsim's EEPROM model treats writes as instantaneous;
//! silicon takes 2..5 ms (DS40001303H §7.4 / DS39632E §7.4
//! "Data EEPROM Erase/Write Time").  For Phase-2 the model
//! schedules a fixed 12 000 Tcy delay (~4 ms at the K20's
//! 3 MIPS Fcy or ~3 ms at the 2455's 4 MIPS Fcy), which is
//! within the documented range.  Phase-3 dual-run will
//! pin the cycle-stamped EEIF assertion against the
//! Datasheet, NOT against gpsim, on the V1.71-baseline
//! "EEPROM image after write" parity.

use crate::memory::{Address, Memory, Variant};

pub const EEDATA_ADDR: u16 = 0xFA8;
pub const EEADR_ADDR: u16 = 0xFA9;
pub const EECON2_ADDR: u16 = 0xFA7;
pub const EECON1_ADDR: u16 = 0xFA6;
pub const PIR2_ADDR: u16 = 0xFA1;

const EECON1_EEPGD: u8 = 1 << 7;
const EECON1_FREE: u8 = 1 << 4;
const EECON1_WRERR: u8 = 1 << 3;
const EECON1_WREN: u8 = 1 << 2;
const EECON1_WR: u8 = 1 << 1;
const EECON1_RD: u8 = 1 << 0;
const PIR2_EEIF: u8 = 1 << 4;

/// Datasheet typical post-write completion in Tcy.  At the
/// K20's 3 MIPS Fcy this is ~4 ms; at the 2455's 4 MIPS
/// Fcy it's ~3 ms.  Both within DS §7.4's documented
/// 2..5 ms range.  Phase-3 may sharpen this per-variant.
const POST_WRITE_TCY: u32 = 12_000;

/// Phase of the EECON2 unlock sequence.  Real silicon
/// requires firmware to write 0x55, then 0xAA, then set
/// EECON1.WR within five instructions or the sequence
/// resets.  Phase-2 doesn't enforce the cycle-window
/// constraint -- any intervening SFR write to EECON2 with
/// the wrong byte resets the sequence, but a delayed WR
/// after the 0xAA still triggers.  Tracked as a known
/// LOW fidelity gap.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
enum UnlockPhase {
    #[default]
    Idle,
    Got55,
    Armed,
}

#[derive(Clone, Debug)]
pub struct Eeprom {
    /// 256-byte backing storage.  Reset behaviour: POR
    /// preserves the previous EEPROM contents (silicon
    /// is non-volatile); Phase-2 emulates this by
    /// storing the bytes inside the struct (separate
    /// from data RAM) and never wiping them across
    /// resets.
    storage: Box<[u8; 256]>,
    /// Tcy remaining until the in-flight write completes.
    /// `None` means no write in flight.
    pending_tcy: Option<u32>,
    /// Address latched at write-trigger time -- silicon
    /// commits to that address regardless of subsequent
    /// firmware EEADR mutations.
    pending_addr: u8,
    /// Data byte latched at write-trigger time.
    pending_data: u8,
    /// EECON2 unlock sequencer state.
    unlock: UnlockPhase,
}

impl Default for Eeprom {
    fn default() -> Self {
        Eeprom {
            storage: Box::new([0u8; 256]),
            pending_tcy: None,
            pending_addr: 0,
            pending_data: 0,
            unlock: UnlockPhase::Idle,
        }
    }
}

impl Eeprom {
    pub fn new(_variant: Variant) -> Self {
        Eeprom::default()
    }

    pub fn reset_state(&mut self) {
        // EEPROM contents are non-volatile.  The
        // post-write timer drops, the unlock sequencer
        // resets, but the storage bytes survive.
        self.pending_tcy = None;
        self.pending_addr = 0;
        self.pending_data = 0;
        self.unlock = UnlockPhase::Idle;
    }

    /// Inject EEPROM contents (e.g. for boot fixtures).
    /// Phase-3 hex loader will populate this via the
    /// `0xF00000` EEPROM region of the .hex file.
    pub fn set_byte(&mut self, addr: u8, value: u8) {
        self.storage[addr as usize] = value;
    }

    pub fn get_byte(&self, addr: u8) -> u8 {
        self.storage[addr as usize]
    }

    pub fn on_sfr_write(&mut self, addr: u16, value: u8, mem: &mut Memory) {
        match addr {
            EECON2_ADDR => self.handle_eecon2_write(value),
            EECON1_ADDR => self.handle_eecon1_write(value, mem),
            EEDATA_ADDR | EEADR_ADDR => {}
            _ => {
                // Any non-EECON2 SFR write doesn't progress
                // the unlock sequencer; we leave it where
                // it is.  EECON2's own handler resets on
                // wrong byte.  This matches silicon's "any
                // other SFR write between 0x55 and 0xAA
                // doesn't reset the sequencer, but a wrong
                // EECON2 byte does" rule.
            }
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
        // Write completes.
        self.pending_tcy = None;
        self.storage[self.pending_addr as usize] = self.pending_data;
        // Clear EECON1.WR.
        let con1 = mem.read_raw(Address::from_raw(EECON1_ADDR));
        mem.write_raw(
            Address::from_raw(EECON1_ADDR),
            con1 & !EECON1_WR,
        );
        // Assert PIR2.EEIF.
        let pir2 = mem.read_raw(Address::from_raw(PIR2_ADDR));
        mem.write_raw(
            Address::from_raw(PIR2_ADDR),
            pir2 | PIR2_EEIF,
        );
    }

    fn handle_eecon2_write(&mut self, value: u8) {
        // EECON2 unlock state machine: 0x55 -> 0xAA arms.
        // Wrong byte resets.
        match (self.unlock.clone(), value) {
            (UnlockPhase::Idle, 0x55) => self.unlock = UnlockPhase::Got55,
            (UnlockPhase::Got55, 0xAA) => self.unlock = UnlockPhase::Armed,
            _ => self.unlock = UnlockPhase::Idle,
        }
    }

    fn handle_eecon1_write(&mut self, value: u8, mem: &mut Memory) {
        // RD path: an EEPGD=0 + RD=1 write reads the EEPROM
        // byte at EEADR into EEDATA.  Phase-2 simplifies
        // by treating the read as instantaneous (real
        // silicon is also "next instruction cycle"), and
        // RD self-clears.  The clear-back to EECON1 must
        // operate on the *post-mask* memory byte (read it
        // back) so we don't leak unimplemented bit 5 from
        // the firmware-intended `value` parameter.
        if (value & EECON1_RD) != 0 && (value & EECON1_EEPGD) == 0 {
            let eeadr = mem.read_raw(Address::from_raw(EEADR_ADDR));
            let byte = self.storage[eeadr as usize];
            mem.write_raw(Address::from_raw(EEDATA_ADDR), byte);
            let cur = mem.read_raw(Address::from_raw(EECON1_ADDR));
            mem.write_raw(
                Address::from_raw(EECON1_ADDR),
                cur & !EECON1_RD,
            );
        }
        // WR path: EEPGD=0 + WREN=1 + WR=1 + unlock armed.
        // The unlock sequencer resets after consuming.
        if (value & EECON1_WR) != 0
            && (value & EECON1_EEPGD) == 0
            && (value & EECON1_WREN) != 0
        {
            if self.unlock == UnlockPhase::Armed && self.pending_tcy.is_none() {
                self.pending_addr = mem.read_raw(Address::from_raw(EEADR_ADDR));
                self.pending_data = mem.read_raw(Address::from_raw(EEDATA_ADDR));
                self.pending_tcy = Some(POST_WRITE_TCY);
                self.unlock = UnlockPhase::Idle;
            } else {
                // Not armed -- silicon sets WRERR (write
                // error flag) and refuses the write.  WR
                // does NOT auto-clear in this case.  Use
                // the post-mask memory byte (cur), not the
                // firmware-intended `value`, so bit 5 stays
                // 0.
                let cur = mem.read_raw(Address::from_raw(EECON1_ADDR));
                mem.write_raw(
                    Address::from_raw(EECON1_ADDR),
                    cur | EECON1_WRERR,
                );
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fresh_mem() -> Memory {
        Memory::new(Variant::Pic18F25K20)
    }

    fn arm_unlock(ee: &mut Eeprom) {
        ee.handle_eecon2_write(0x55);
        ee.handle_eecon2_write(0xAA);
        assert_eq!(ee.unlock, UnlockPhase::Armed);
    }

    #[test]
    fn idle_tick_does_nothing() {
        let mut ee = Eeprom::default();
        let mut mem = fresh_mem();
        ee.tick_tcy(100_000, &mut mem);
        assert!(ee.pending_tcy.is_none());
    }

    #[test]
    fn unlock_55_aa_arms_sequencer() {
        let mut ee = Eeprom::default();
        ee.handle_eecon2_write(0x55);
        assert_eq!(ee.unlock, UnlockPhase::Got55);
        ee.handle_eecon2_write(0xAA);
        assert_eq!(ee.unlock, UnlockPhase::Armed);
    }

    #[test]
    fn wrong_unlock_byte_resets_sequencer() {
        let mut ee = Eeprom::default();
        ee.handle_eecon2_write(0x55);
        ee.handle_eecon2_write(0x12); // not 0xAA
        assert_eq!(ee.unlock, UnlockPhase::Idle);
    }

    #[test]
    fn wr_without_unlock_sets_wrerr_no_write() {
        let mut ee = Eeprom::default();
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(EEADR_ADDR), 0x10);
        mem.write_raw(Address::from_raw(EEDATA_ADDR), 0xAB);
        // EECON1 = WREN | WR (no unlock).
        let con1 = EECON1_WREN | EECON1_WR;
        mem.write_raw(Address::from_raw(EECON1_ADDR), con1);
        ee.handle_eecon1_write(con1, &mut mem);
        let new_con1 = mem.read_raw(Address::from_raw(EECON1_ADDR));
        assert_eq!(new_con1 & EECON1_WRERR, EECON1_WRERR);
        assert!(ee.pending_tcy.is_none());
        assert_eq!(ee.storage[0x10], 0, "EEPROM unchanged on rejected write");
    }

    #[test]
    fn unlocked_wr_schedules_post_write_timer() {
        let mut ee = Eeprom::default();
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(EEADR_ADDR), 0x42);
        mem.write_raw(Address::from_raw(EEDATA_ADDR), 0x55);
        arm_unlock(&mut ee);
        let con1 = EECON1_WREN | EECON1_WR;
        mem.write_raw(Address::from_raw(EECON1_ADDR), con1);
        ee.handle_eecon1_write(con1, &mut mem);
        assert_eq!(ee.pending_tcy, Some(POST_WRITE_TCY));
        assert_eq!(ee.pending_addr, 0x42);
        assert_eq!(ee.pending_data, 0x55);
        // Unlock sequence consumed.
        assert_eq!(ee.unlock, UnlockPhase::Idle);
    }

    #[test]
    fn write_completes_clears_wr_sets_eeif_stores_byte() {
        let mut ee = Eeprom::default();
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(EEADR_ADDR), 0x80);
        mem.write_raw(Address::from_raw(EEDATA_ADDR), 0xCD);
        arm_unlock(&mut ee);
        let con1 = EECON1_WREN | EECON1_WR;
        mem.write_raw(Address::from_raw(EECON1_ADDR), con1);
        ee.handle_eecon1_write(con1, &mut mem);
        // Tick past the post-write window.
        ee.tick_tcy(POST_WRITE_TCY + 1, &mut mem);
        assert!(ee.pending_tcy.is_none());
        let con1_after = mem.read_raw(Address::from_raw(EECON1_ADDR));
        assert_eq!(con1_after & EECON1_WR, 0);
        let pir2 = mem.read_raw(Address::from_raw(PIR2_ADDR));
        assert_eq!(pir2 & PIR2_EEIF, PIR2_EEIF);
        assert_eq!(ee.storage[0x80], 0xCD);
    }

    #[test]
    fn rd_loads_eedata_from_storage() {
        let mut ee = Eeprom::default();
        let mut mem = fresh_mem();
        ee.set_byte(0x40, 0x99);
        mem.write_raw(Address::from_raw(EEADR_ADDR), 0x40);
        // EECON1 = RD (with EEPGD=0).
        let con1 = EECON1_RD;
        mem.write_raw(Address::from_raw(EECON1_ADDR), con1);
        ee.handle_eecon1_write(con1, &mut mem);
        assert_eq!(
            mem.read_raw(Address::from_raw(EEDATA_ADDR)),
            0x99,
        );
        // RD self-cleared.
        assert_eq!(
            mem.read_raw(Address::from_raw(EECON1_ADDR)) & EECON1_RD,
            0,
        );
    }

    /// Regression: the EEPROM hook's RD-self-clear and
    /// WRERR-set paths must NOT leak unimplemented bit 5
    /// of EECON1 from the firmware-intended `value`
    /// parameter into SFR memory.  Set bit 5 in `value`
    /// alongside RD or WR, and confirm bit 5 stays cleared
    /// in EECON1 after the hook runs.
    #[test]
    fn unimplemented_eecon1_bit5_does_not_leak_via_hook() {
        // Path 1: RD self-clear must not set bit 5.
        let mut ee = Eeprom::default();
        let mut mem = fresh_mem();
        // Pre-condition: memory[EECON1] starts at 0 (POR).
        // Firmware-intended `value` includes bit 5 set.
        let value = EECON1_RD | (1 << 5);
        ee.handle_eecon1_write(value, &mut mem);
        let con1 = mem.read_raw(Address::from_raw(EECON1_ADDR));
        assert_eq!(con1 & (1 << 5), 0, "bit 5 must not leak via RD path");

        // Path 2: WRERR-set on bad unlock must not set bit 5.
        let mut ee = Eeprom::default();
        let mut mem = fresh_mem();
        let value = EECON1_WREN | EECON1_WR | (1 << 5);
        ee.handle_eecon1_write(value, &mut mem);
        let con1 = mem.read_raw(Address::from_raw(EECON1_ADDR));
        assert_eq!(con1 & EECON1_WRERR, EECON1_WRERR);
        assert_eq!(con1 & (1 << 5), 0, "bit 5 must not leak via WRERR path");
    }

    #[test]
    fn reset_state_drops_in_flight_but_preserves_storage() {
        let mut ee = Eeprom::default();
        let mut mem = fresh_mem();
        ee.set_byte(0x10, 0xDE);
        ee.set_byte(0x11, 0xAD);
        // Start a write.
        mem.write_raw(Address::from_raw(EEADR_ADDR), 0x20);
        mem.write_raw(Address::from_raw(EEDATA_ADDR), 0x42);
        arm_unlock(&mut ee);
        let con1 = EECON1_WREN | EECON1_WR;
        ee.handle_eecon1_write(con1, &mut mem);
        assert!(ee.pending_tcy.is_some());
        // Reset.
        ee.reset_state();
        assert!(ee.pending_tcy.is_none());
        assert_eq!(ee.unlock, UnlockPhase::Idle);
        // Storage survived.
        assert_eq!(ee.get_byte(0x10), 0xDE);
        assert_eq!(ee.get_byte(0x11), 0xAD);
        // The aborted write byte (0x42 at 0x20) was NEVER
        // committed -- confirm.
        assert_eq!(ee.get_byte(0x20), 0);
    }
}
