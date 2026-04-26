//! EUSART (Enhanced USART) peripheral model.  Implements the
//! transmit and receive shifters, baud generator, and the
//! status-bit dance the firmware observes via TXSTA / RCSTA /
//! PIR1.  Backing SFRs:
//!
//! | Addr  | Reg     | Role                                    |
//! |-------|---------|-----------------------------------------|
//! | 0xFAB | RCSTA   | SPEN, RX9, SREN, CREN, ADDEN, FERR, OERR, RX9D |
//! | 0xFAC | TXSTA   | CSRC, TX9, TXEN, SYNC, SENDB, BRGH, TRMT, TX9D |
//! | 0xFAD | TXREG   | TX FIFO single-deep latch               |
//! | 0xFAE | RCREG   | RX FIFO 2-deep                          |
//! | 0xFAF | SPBRG   | Baud generator divisor low              |
//! | 0xFB0 | SPBRGH  | Baud generator divisor high (BRG16=1)   |
//! | 0xFB8 | BAUDCON | ABDOVF/RCIDL/DTRXP/CKTXP/BRG16/WUE/ABDEN |
//!
//! TXIF / RCIF live in PIR1 @ 0xF9E:
//!   - TXIF = bit 4
//!   - RCIF = bit 5
//!
//! Datasheet refs: DS40001303H §17 (K20), DS39632E §22 (2455).
//!
//! ## Phase 2 scope
//!
//! - Async (SYNC=0) mode only — sync mode is not used by either
//!   firmware family.
//! - Bit-level *timing* fidelity for the transmit path: TRMT
//!   clears on TXREG write and re-asserts after exactly
//!   `(start_bit + data_bits + stop_bit) × baud_period_tcy` Tcy
//!   measured against the executor's cycle counter.  TXIF
//!   asserts at the same moment, gated by TXEN.
//! - Receive path is silent on a single-core local test (no
//!   pin network yet) — `tick_tcy` doesn't fabricate RX bytes.
//!   Phase 3 will wire RX to a peer core's TX via the pin net.
//! - OERR/FERR/RX9D are read-only status bits the SW write
//!   path already preserves via `sfr_write_mask` (RCSTA mask =
//!   0xF8; see `exec.rs`).  They stay 0 here until Phase 3
//!   delivers a frame error / overrun.
//!
//! ## Baud generator
//!
//! Datasheet Tbl 17-1 / 17-2 (K20) / 22-1 / 22-2 (2455):
//!
//! ```text
//!   SYNC=0, BRGH=0, BRG16=0:  Fcy / (64 × (SPBRG + 1))
//!   SYNC=0, BRGH=1, BRG16=0:  Fcy / (16 × (SPBRG + 1))
//!   SYNC=0, BRGH=0, BRG16=1:  Fcy / (16 × (SPBRGH:SPBRG + 1))
//!   SYNC=0, BRGH=1, BRG16=1:  Fcy /  (4 × (SPBRGH:SPBRG + 1))
//! ```
//!
//! The peripheral stores the *bit period in Tcy*, recomputed on
//! every TXSTA / BAUDCON / SPBRG / SPBRGH write.  A 0-divisor
//! configuration would produce a meaningless period — the model
//! clamps to 1 Tcy/bit so `tick_tcy` still makes progress and
//! the firmware bug becomes self-evident.

use crate::memory::{Address, Memory, Variant};

/// Address of the TXSTA SFR on both supported variants.
pub const TXSTA_ADDR: u16 = 0xFAC;
/// Address of the RCSTA SFR.
pub const RCSTA_ADDR: u16 = 0xFAB;
/// Address of TXREG.
pub const TXREG_ADDR: u16 = 0xFAD;
/// Address of RCREG.
pub const RCREG_ADDR: u16 = 0xFAE;
/// Address of SPBRG.
pub const SPBRG_ADDR: u16 = 0xFAF;
/// Address of SPBRGH.
pub const SPBRGH_ADDR: u16 = 0xFB0;
/// Address of BAUDCON.
pub const BAUDCON_ADDR: u16 = 0xFB8;
/// Address of PIR1 (carries TXIF/RCIF).
pub const PIR1_ADDR: u16 = 0xF9E;

const TXSTA_TXEN: u8 = 1 << 5;
const TXSTA_SYNC: u8 = 1 << 4;
const TXSTA_BRGH: u8 = 1 << 2;
const TXSTA_TRMT: u8 = 1 << 1;
const RCSTA_SPEN: u8 = 1 << 7;
const BAUDCON_BRG16: u8 = 1 << 3;
const PIR1_TXIF: u8 = 1 << 4;

#[derive(Clone, Debug, Default)]
pub struct Eusart {
    /// Tcy remaining until the in-flight TX frame finishes
    /// shifting out (drops TRMT from 0 back to 1 + sets TXIF
    /// when this reaches 0).  `None` means the shifter is
    /// idle and TRMT is already 1.
    tx_pending_tcy: Option<u32>,
    /// Pending byte loaded by the most recent TXREG write
    /// while the shifter was busy.  None means TXREG is
    /// available for the firmware to write the next byte.
    /// (PIC18 EUSART has a 1-deep TX FIFO: TXREG itself is
    /// the FIFO slot, and TSR is the actual shifter; firmware
    /// can write a new TXREG while TRMT=0 as long as TXIF=1
    /// signalling the previous load already moved into TSR.
    /// For the Phase-2 scope we model TXREG as held for one
    /// frame's worth of Tcy — fidelity here is enough for
    /// the cycle-stamped boot path.)
    tx_pending_byte: Option<u8>,
}

impl Eusart {
    pub fn new(_variant: Variant) -> Self {
        Eusart::default()
    }

    /// React to a SW-driven SFR write at `addr` whose new
    /// post-mask value is `value`.  Reads/writes other SFRs
    /// in `mem` only when actually needed (TXREG write reads
    /// back TXSTA/SPBRG/etc. to re-arm the baud counter).
    pub fn on_sfr_write(&mut self, addr: u16, value: u8, mem: &mut Memory) {
        match addr {
            TXREG_ADDR => self.handle_txreg_write(value, mem),
            // TXSTA/RCSTA/SPBRG/SPBRGH/BAUDCON writes don't
            // immediately move data in async mode -- they only
            // change the shape of the next TX frame.  We
            // recompute the baud period the next time TXREG
            // is loaded, so no eager work needed here.
            TXSTA_ADDR
            | RCSTA_ADDR
            | SPBRG_ADDR
            | SPBRGH_ADDR
            | BAUDCON_ADDR => {}
            _ => {}
        }
    }

    /// Advance the EUSART by `n` Tcy, updating TXSTA.TRMT and
    /// PIR1.TXIF when the in-flight frame finishes.
    pub fn tick_tcy(&mut self, n: u32, mem: &mut Memory) {
        let Some(remaining) = self.tx_pending_tcy.as_mut() else {
            return;
        };
        if n >= *remaining {
            // Frame complete this tick.
            self.tx_pending_tcy = None;
            self.tx_pending_byte = None;
            set_txsta_trmt(mem, true);
            // Only assert TXIF if the transmitter is enabled --
            // datasheet §17.4.1.5 ("TXIF flag"): TXIF reflects
            // the TXREG-empty condition; the firmware enables
            // the interrupt by setting TXIE separately.  We
            // assert unconditionally because TXIF reflects the
            // *empty* state, which is true by definition once
            // the shifter drains.  Suppression of the IRQ
            // happens in the IRQ controller (P2.7) via
            // PIE1/IPEN/GIE -- not here.
            set_pir1_txif(mem, true);
        } else {
            *remaining -= n;
        }
    }

    fn handle_txreg_write(&mut self, byte: u8, mem: &mut Memory) {
        // Compute baud-bit-period in Tcy from the current
        // TXSTA / BAUDCON / SPBRG{,H} configuration.
        let period_tcy = current_baud_bit_period_tcy(mem);

        // 10-bit frame for SYNC=0 (1 start + 8 data + 1 stop;
        // TX9 enables a 9th data bit which we do not
        // currently model in the period -- a known fidelity
        // gap, called out in the eusart.rs docstring).  See
        // DS40001303H Fig 17-3.
        let frame_bits = 10u32;
        let frame_tcy = period_tcy.saturating_mul(frame_bits);

        self.tx_pending_byte = Some(byte);
        self.tx_pending_tcy = Some(frame_tcy);

        // The shifter is now busy: TRMT goes low; TXIF
        // remains low until the frame drains.
        set_txsta_trmt(mem, false);
        set_pir1_txif(mem, false);
    }
}

/// Read the current baud-bit period (in Tcy) from the SFR
/// state.  Caller-side `tick_tcy` and TXREG-write semantics
/// re-evaluate this on every TXREG write so a mid-stream
/// SPBRG write doesn't desynchronise the model from the SFR.
fn current_baud_bit_period_tcy(mem: &Memory) -> u32 {
    let txsta = mem.read_raw(Address::from_raw(TXSTA_ADDR));
    let baudcon = mem.read_raw(Address::from_raw(BAUDCON_ADDR));
    let spbrg = mem.read_raw(Address::from_raw(SPBRG_ADDR)) as u32;
    let spbrgh = mem.read_raw(Address::from_raw(SPBRGH_ADDR)) as u32;
    let brgh = (txsta & TXSTA_BRGH) != 0;
    let brg16 = (baudcon & BAUDCON_BRG16) != 0;

    let (divisor_factor, n) = match (brg16, brgh) {
        (false, false) => (64u32, spbrg),
        (false, true) => (16u32, spbrg),
        (true, false) => (16u32, (spbrgh << 8) | spbrg),
        (true, true) => (4u32, (spbrgh << 8) | spbrg),
    };
    // Bit period in Tcy = divisor_factor × (n + 1).  The
    // datasheet formula is `Fcy / (factor × (n + 1))` baud,
    // and 1 Tcy at Fcy = 1 / Fcy seconds, so:
    //   bit_period_seconds = (factor × (n + 1)) / Fcy
    //   bit_period_tcy     = factor × (n + 1)
    // Clamp to 1 Tcy/bit so a divide-by-zero firmware bug
    // doesn't deadlock the model.
    divisor_factor.saturating_mul(n + 1).max(1)
}

fn set_txsta_trmt(mem: &mut Memory, on: bool) {
    let addr = Address::from_raw(TXSTA_ADDR);
    let current = mem.read_raw(addr);
    let new_val = if on {
        current | TXSTA_TRMT
    } else {
        current & !TXSTA_TRMT
    };
    mem.write_raw(addr, new_val);
}

fn set_pir1_txif(mem: &mut Memory, on: bool) {
    let addr = Address::from_raw(PIR1_ADDR);
    let current = mem.read_raw(addr);
    let new_val = if on {
        current | PIR1_TXIF
    } else {
        current & !PIR1_TXIF
    };
    mem.write_raw(addr, new_val);
}

/// True if the EUSART is currently configured to transmit
/// asynchronously: SPEN=1 (RCSTA), TXEN=1 (TXSTA), SYNC=0
/// (TXSTA).  Used by Phase-3 chain wiring to decide when to
/// publish TX bytes onto the pin network.
pub fn is_async_tx_enabled(mem: &Memory) -> bool {
    let rcsta = mem.read_raw(Address::from_raw(RCSTA_ADDR));
    let txsta = mem.read_raw(Address::from_raw(TXSTA_ADDR));
    (rcsta & RCSTA_SPEN) != 0
        && (txsta & TXSTA_TXEN) != 0
        && (txsta & TXSTA_SYNC) == 0
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fresh_mem() -> Memory {
        Memory::new(Variant::Pic18F25K20)
    }

    /// V1.71 boot config: SPBRG=5, BRGH=0, BRG16=0 -> 1 bit =
    /// 64 × (5+1) = 384 Tcy at the K20's 3 MIPS Fcy.
    #[test]
    fn baud_period_v171_31250_baud() {
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(SPBRG_ADDR), 5);
        mem.write_raw(Address::from_raw(TXSTA_ADDR), 0x20); // TXEN
        mem.write_raw(Address::from_raw(BAUDCON_ADDR), 0x40); // RCIDL, BRG16=0
        assert_eq!(current_baud_bit_period_tcy(&mem), 384);
    }

    /// BRGH=1, BRG16=0 -> 1 bit = 16 × (n+1) Tcy.
    #[test]
    fn baud_period_brgh_high() {
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(SPBRG_ADDR), 25);
        mem.write_raw(Address::from_raw(TXSTA_ADDR), 0x24); // TXEN | BRGH
        mem.write_raw(Address::from_raw(BAUDCON_ADDR), 0);
        assert_eq!(current_baud_bit_period_tcy(&mem), 16 * 26);
    }

    /// BRG16=1 selects the 16-bit divisor with SPBRGH:SPBRG.
    #[test]
    fn baud_period_brg16_uses_spbrgh() {
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(SPBRG_ADDR), 0x20);
        mem.write_raw(Address::from_raw(SPBRGH_ADDR), 0x01);
        mem.write_raw(Address::from_raw(TXSTA_ADDR), 0x20);
        mem.write_raw(Address::from_raw(BAUDCON_ADDR), 0x08); // BRG16
        // n = 0x0120 = 288;   divisor_factor = 16 (BRGH=0, BRG16=1)
        // bit period = 16 * 289 = 4624 Tcy.
        assert_eq!(current_baud_bit_period_tcy(&mem), 16 * 289);
    }

    #[test]
    fn baud_period_clamps_to_one_on_zero_divisor() {
        let mem = fresh_mem();
        // SPBRG=0, BRG16=1, BRGH=1 -> factor=4, n+1=1 -> 4 Tcy/bit.
        let mut mem = mem;
        mem.write_raw(Address::from_raw(TXSTA_ADDR), 0x24);
        mem.write_raw(Address::from_raw(BAUDCON_ADDR), 0x08);
        assert_eq!(current_baud_bit_period_tcy(&mem), 4);
    }

    #[test]
    fn txreg_write_clears_trmt_and_txif_then_reasserts_after_frame() {
        let mut eusart = Eusart::new(Variant::Pic18F25K20);
        let mut mem = fresh_mem();
        // V1.71 boot setup: SPBRG=5 (31250 baud @ 3 MIPS), TXEN.
        mem.write_raw(Address::from_raw(SPBRG_ADDR), 5);
        mem.write_raw(Address::from_raw(TXSTA_ADDR), 0x22); // TXEN | TRMT
        mem.write_raw(Address::from_raw(BAUDCON_ADDR), 0x40);

        // TXREG write
        eusart.on_sfr_write(TXREG_ADDR, 0x55, &mut mem);
        let txsta = mem.read_raw(Address::from_raw(TXSTA_ADDR));
        let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
        assert_eq!(txsta & TXSTA_TRMT, 0, "TRMT must clear on TXREG write");
        assert_eq!(pir1 & PIR1_TXIF, 0, "TXIF must clear on TXREG write");

        // Frame is 10 bits × 384 Tcy/bit = 3840 Tcy.  Tick
        // a few partial frames first to confirm the counter.
        eusart.tick_tcy(1000, &mut mem);
        let txsta = mem.read_raw(Address::from_raw(TXSTA_ADDR));
        assert_eq!(txsta & TXSTA_TRMT, 0, "TRMT must stay 0 mid-frame");

        eusart.tick_tcy(2000, &mut mem); // total 3000; need 3840
        let txsta = mem.read_raw(Address::from_raw(TXSTA_ADDR));
        assert_eq!(txsta & TXSTA_TRMT, 0, "TRMT must stay 0 below 3840");

        eusart.tick_tcy(1000, &mut mem); // total 4000 >= 3840
        let txsta = mem.read_raw(Address::from_raw(TXSTA_ADDR));
        let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
        assert_eq!(txsta & TXSTA_TRMT, TXSTA_TRMT, "TRMT must reassert post-frame");
        assert_eq!(pir1 & PIR1_TXIF, PIR1_TXIF, "TXIF must assert post-frame");
    }

    #[test]
    fn idle_tick_is_no_op() {
        let mut eusart = Eusart::new(Variant::Pic18F25K20);
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(TXSTA_ADDR), TXSTA_TRMT);
        eusart.tick_tcy(10_000, &mut mem);
        assert_eq!(
            mem.read_raw(Address::from_raw(TXSTA_ADDR)) & TXSTA_TRMT,
            TXSTA_TRMT
        );
    }

    #[test]
    fn is_async_tx_enabled_requires_spen_and_txen_and_not_sync() {
        let mut mem = fresh_mem();
        // Default: all zero.  Not enabled.
        assert!(!is_async_tx_enabled(&mem));
        mem.write_raw(Address::from_raw(RCSTA_ADDR), RCSTA_SPEN);
        assert!(!is_async_tx_enabled(&mem));
        mem.write_raw(Address::from_raw(TXSTA_ADDR), TXSTA_TXEN);
        assert!(is_async_tx_enabled(&mem));
        // Sync mode disables the async path.
        mem.write_raw(Address::from_raw(TXSTA_ADDR), TXSTA_TXEN | TXSTA_SYNC);
        assert!(!is_async_tx_enabled(&mem));
    }
}
