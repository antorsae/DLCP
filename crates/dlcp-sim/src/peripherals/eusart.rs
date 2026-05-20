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
//! Datasheet Tbl 17-1 / 17-2 (K20) / 22-1 / 22-2 (2455) gives
//! the formulas in *FOSC* terms:
//!
//! ```text
//!   SYNC=0, BRGH=0, BRG16=0:  Baud = FOSC / (64 × (SPBRG + 1))
//!   SYNC=0, BRGH=1, BRG16=0:  Baud = FOSC / (16 × (SPBRG + 1))
//!   SYNC=0, BRGH=0, BRG16=1:  Baud = FOSC / (16 × (SPBRGH:SPBRG + 1))
//!   SYNC=0, BRGH=1, BRG16=1:  Baud = FOSC /  (4 × (SPBRGH:SPBRG + 1))
//! ```
//!
//! Converting to *Tcy* (FOSC / 4 -> Tcy = 4 FOSC cycles):
//!
//! ```text
//!   bit_period_seconds = factor_FOSC × (n + 1) / FOSC
//!   bit_period_tcy     = bit_period_seconds × Fcy
//!                      = factor_FOSC × (n + 1) / 4
//! ```
//!
//! So in *Tcy units* the divisor factors collapse to
//! `{16, 4, 4, 1}` for `(BRGH, BRG16) ∈ {(0,0), (1,0), (0,1),
//! (1,1)}`.  V1.71's SPBRG=5 / BRGH=0 / BRG16=0 -> 16 × 6 = 96
//! Tcy/bit, matching the 31250 baud at 3 MIPS Fcy
//! (3e6 / 31250 = 96).
//!
//! The peripheral stores the *bit period in Tcy*, recomputed on
//! every TXREG load.  A 0-divisor configuration would produce a
//! meaningless period — the model clamps to 1 Tcy/bit so
//! `tick_tcy` still makes progress and the firmware bug becomes
//! self-evident.

use std::collections::VecDeque;

use crate::memory::{Address, Memory, Variant};
use serde::{Deserialize, Serialize};

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
const TXSTA_SENDB: u8 = 1 << 3;
const TXSTA_TX9: u8 = 1 << 6;
const TXSTA_BRGH: u8 = 1 << 2;
const TXSTA_TRMT: u8 = 1 << 1;
const RCSTA_SPEN: u8 = 1 << 7;
const RCSTA_RX9: u8 = 1 << 6;
const BAUDCON_BRG16: u8 = 1 << 3;
const BAUDCON_WUE: u8 = 1 << 1;
const PIR1_TXIF: u8 = 1 << 4;
const PIR1_RCIF: u8 = 1 << 5;

/// RCSTA.CREN (Continuous Receive Enable, bit 4).
const RCSTA_CREN: u8 = 1 << 4;

/// RCSTA.OERR (Overrun Error, bit 1).  Sticky; cleared by
/// firmware writing CREN=0 or by software-resetting the
/// EUSART.
const RCSTA_OERR: u8 = 1 << 1;
const RCSTA_FERR: u8 = 1 << 2;
const RCSTA_RX9D: u8 = 1 << 0;

/// Depth of the silicon RX FIFO behind RCREG.  Per DS39632E
/// §20.0 the EUSART has a "two character deep FIFO".  Our
/// model uses a small fixed array so the per-byte path
/// stays heap-free.
const RX_FIFO_DEPTH: usize = 2;

#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq)]
struct RxEntry {
    byte: u8,
    ferr: bool,
    rx9d: bool,
}

/// Result of `Eusart::deliver_rx_byte` / `deliver_rx_frame`.
/// Splits the existing single-bool wake hint into the wake
/// hint AND a separate `accepted` flag so the chain's UART
/// dispatch can record FIFO-accepted bytes (`uart_rx_history`)
/// distinct from wire-attempts (`uart_tx_history`).  Task #94.
///
/// `accepted == true` iff the byte was pushed into the silicon
/// FIFO behind RCREG (SPEN+CREN gate passed AND no OERR latched
/// AND FIFO had room).  `accepted == false` covers the three
/// drop paths: SPEN/CREN clear, OERR sticky, FIFO full (which
/// also latches OERR as a side-effect).  `wake` retains the
/// existing semantic: BAUDCON.WUE-driven wake hint that the
/// chain dispatcher uses to bring halted destination cores
/// back to `RunState::Running`.
#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq, Default)]
pub struct RxDelivery {
    pub wake: bool,
    pub accepted: bool,
}

#[derive(Serialize, Deserialize, Clone, Debug, Default)]
pub struct Eusart {
    /// Tcy remaining until the in-flight TX shift register
    /// (TSR) finishes shifting out the current byte.  Drops
    /// TXSTA.TRMT from 0 back to 1 when this reaches 0.
    /// `None` means TSR is idle and TRMT is already 1.
    tsr_busy_tcy: Option<u32>,
    /// Byte currently held in TSR (the shift register).
    /// `None` when TSR is idle.  Phase-3.5 chain dispatch
    /// reads this when the frame drains so the
    /// firmware-emitted byte can be propagated to the peer
    /// core's EUSART RX via the pin network.
    tsr_byte: Option<u8>,
    tsr_send_break: bool,
    /// Byte queued in TXREG while TSR was busy (PIC18 EUSART
    /// has a 1-deep TX FIFO: TXREG holds the next byte while
    /// TSR shifts the current one).  `None` means TXREG is
    /// empty and TXIF should be asserted (assuming TXEN=1).
    txreg_holding: Option<u8>,
    txreg_holding_send_break: bool,
    /// TXIF is not valid until the second instruction cycle
    /// after TXREG transfers into TSR (datasheet EUSART TXIF
    /// note).  While non-zero, PIR1.TXIF is forced low even
    /// if TXREG is empty.
    txif_delay_tcy: u8,
    /// FIFO of bytes that have completed TX and are waiting
    /// to be drained by the chain dispatcher (Phase-3.5
    /// `Chain::execute_core_step` pulls them via
    /// `take_completed_tx_byte` and posts a
    /// `PinPropagation` event for each matching UART
    /// coupling).  Bytes accumulate here in TX order; the
    /// chain consumes them in the same order.
    completed_tx_bytes: VecDeque<u8>,
    /// Silicon RX FIFO behind RCREG.  Per DS39632E §20.0 the
    /// EUSART has a "two character deep FIFO".  Bytes are
    /// pushed here on `deliver_rx_byte` and popped on RCREG
    /// read.  RCIF tracks "FIFO non-empty"; OERR latches
    /// when a third byte arrives while the FIFO is full
    /// (the third byte is dropped per DS §20.4.4).  Without
    /// this depth, V3.1's chain protocol parser sees only
    /// the latest byte after each ISR-latency window,
    /// turning intact `B1 04 00` frames into phase-shifted
    /// debris -- the cmd/data bytes are lost before the
    /// firmware reads them.  Task #30.
    rx_fifo: VecDeque<RxEntry>,
}

impl Eusart {
    pub fn new(_variant: Variant) -> Self {
        Eusart::default()
    }

    /// Throw away any in-flight TX frame and queued TXREG
    /// byte.  Called from `apply_reset` for POR/BOR/MCLR/WDT/
    /// RESET so a frame in flight when the reset fires
    /// doesn't survive into the post-reset world to mutate
    /// SFRs after the boot vector starts running again.
    pub fn reset_state(&mut self) {
        self.tsr_busy_tcy = None;
        self.tsr_byte = None;
        self.tsr_send_break = false;
        self.txreg_holding = None;
        self.txreg_holding_send_break = false;
        self.txif_delay_tcy = 0;
        self.completed_tx_bytes.clear();
        self.rx_fifo.clear();
    }

    /// Current RX FIFO occupancy (0..=RX_FIFO_DEPTH = 0..=2).
    /// Read-only accessor for diagnostic probes (e.g. P3.6b
    /// research probe) that need to distinguish "byte
    /// accepted into FIFO and waiting for RCREG drain" from
    /// "FIFO empty (parser already drained)" without reading
    /// the SFR-visible RCREG (which always shows the OLDEST
    /// buffered byte regardless of depth).
    #[inline]
    pub fn rx_fifo_depth(&self) -> usize {
        self.rx_fifo.len()
    }

    /// Drain one completed TX byte from the FIFO, or
    /// `None` if no byte has finished shifting since the
    /// last call.  Called by the chain dispatcher after
    /// each `execute_core_step` to propagate emitted bytes
    /// to peer cores via the pin network.
    pub fn take_completed_tx_byte(&mut self) -> Option<u8> {
        self.completed_tx_bytes.pop_front()
    }

    /// Inject a byte directly into the completed-TX FIFO.
    /// Test-only escape hatch so chain-level regression
    /// tests can exercise `drain_completed_tx_bytes`
    /// without running a full 960-Tcy frame through the
    /// executor.  The naming follows
    /// `Core::reset_cycles_for_test`.
    pub fn push_completed_tx_byte_for_test(&mut self, byte: u8) {
        self.completed_tx_bytes.push_back(byte);
    }

    /// Deliver an inbound RX byte from the pin network.
    /// Push into the 2-deep FIFO behind RCREG and assert
    /// `PIR1.RCIF`.  Per DS39632E §20.0 / Reg 9-4 the
    /// silicon FIFO holds two characters; a third byte
    /// arriving while the FIFO is full latches `RCSTA.OERR`
    /// and is dropped (DS §20.4.4).  Once OERR is set the
    /// silicon STOPS accepting further bytes until firmware
    /// clears OERR via `CREN=0` -- even if the firmware
    /// reads RCREG to free FIFO slots, no new bytes land
    /// until OERR is cleared (DS §20.4.4 + DS40001303H Reg
    /// 17-2 OERR description: "no additional characters
    /// are received until the overrun condition is
    /// cleared").  Phase-3.5 minimum: no FERR modeling --
    /// the in-flight RX shifter still arrives whole-frame
    /// at a single moment; Phase-4 dual-run will sharpen
    /// that against gpsim's bit-level RX timing if needed.
    /// Disabled (SPEN=0 or CREN=0) RX silently drops the
    /// byte.  Task #30.
    ///
    /// Returns `RxDelivery { wake, accepted }`:
    ///   * `wake`: BAUDCON.WUE-driven wake hint for halted
    ///     cores (existing semantic; SLEEP/Idle wake on RX
    ///     edge).
    ///   * `accepted`: true iff the byte was pushed into the
    ///     silicon FIFO (i.e. SPEN+CREN gate passed AND no
    ///     OERR latched AND FIFO had room).  Used by the
    ///     chain's `uart_rx_history` recorder to log only
    ///     bytes the destination's silicon accepted.
    ///     Distinct from `uart_tx_history` which records
    ///     wire-attempts pre-acceptance.  See task #94.
    pub fn deliver_rx_byte(&mut self, byte: u8, mem: &mut Memory) -> RxDelivery {
        self.deliver_rx_frame(byte, false, false, mem)
    }

    pub fn deliver_rx_frame(
        &mut self,
        byte: u8,
        framing_error: bool,
        ninth_bit: bool,
        mem: &mut Memory,
    ) -> RxDelivery {
        let rcsta = mem.read_raw(Address::from_raw(RCSTA_ADDR));
        if (rcsta & RCSTA_SPEN) == 0 || (rcsta & RCSTA_CREN) == 0 {
            return RxDelivery {
                wake: false,
                accepted: false,
            };
        }
        let baudcon = mem.read_raw(Address::from_raw(BAUDCON_ADDR));
        let wake = (baudcon & BAUDCON_WUE) != 0;
        if wake {
            mem.write_raw(Address::from_raw(BAUDCON_ADDR), baudcon & !BAUDCON_WUE);
        }
        // OERR latched -> reception blocked until firmware
        // clears OERR (via CREN=0).  Codex review of 4f7deb5
        // MEDIUM: previously we'd accept a fresh byte the
        // moment firmware read RCREG to free a FIFO slot,
        // masking firmware that forgets the CREN-toggle
        // recovery dance.
        if (rcsta & RCSTA_OERR) != 0 {
            return RxDelivery {
                wake,
                accepted: false,
            };
        }
        if self.rx_fifo.len() >= RX_FIFO_DEPTH {
            // FIFO full: latch OERR, drop the byte.  Per DS
            // §20.4.4 OERR clears when firmware writes
            // CREN=0 (handled in `on_sfr_write` for RCSTA).
            mem.write_raw(Address::from_raw(RCSTA_ADDR), rcsta | RCSTA_OERR);
            return RxDelivery {
                wake,
                accepted: false,
            };
        }
        let rx9_enabled = (rcsta & RCSTA_RX9) != 0;
        self.rx_fifo.push_back(RxEntry {
            byte,
            ferr: framing_error,
            rx9d: rx9_enabled && ninth_bit,
        });
        self.update_rx_front_sfrs(mem);
        let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
        mem.write_raw(Address::from_raw(PIR1_ADDR), pir1 | PIR1_RCIF);
        RxDelivery {
            wake,
            accepted: true,
        }
    }

    fn update_rx_front_sfrs(&self, mem: &mut Memory) {
        if let Some(front) = self.rx_fifo.front().copied() {
            mem.write_raw(Address::from_raw(RCREG_ADDR), front.byte);
            let rcsta = mem.read_raw(Address::from_raw(RCSTA_ADDR));
            let mut new_rcsta = rcsta & !(RCSTA_FERR | RCSTA_RX9D);
            if front.ferr {
                new_rcsta |= RCSTA_FERR;
            }
            if front.rx9d {
                new_rcsta |= RCSTA_RX9D;
            }
            mem.write_raw(Address::from_raw(RCSTA_ADDR), new_rcsta);
        } else {
            mem.write_raw(Address::from_raw(RCREG_ADDR), 0);
            let rcsta = mem.read_raw(Address::from_raw(RCSTA_ADDR));
            mem.write_raw(
                Address::from_raw(RCSTA_ADDR),
                rcsta & !(RCSTA_FERR | RCSTA_RX9D),
            );
        }
    }

    /// React to a SW-driven SFR read at `addr`.  Today the
    /// only EUSART SFR with a documented read-side effect is
    /// RCREG: per DS39632E Reg 9-4 (PIR1) bit 5, "RCIF:
    /// EUSART Receive Interrupt Flag bit -- 1 = the EUSART
    /// receive buffer, RCREG, is full (cleared when RCREG is
    /// read); 0 = the EUSART receive buffer is empty."  The
    /// silicon FIFO is 2-deep (DS §20.0 EUSART chapter):
    /// each RCREG read pops the OLDEST byte, leaving the
    /// next byte (if any) staged in RCREG, and clears RCIF
    /// only when the FIFO is now empty.  Without the FIFO
    /// depth, V3.1 MAIN's chain protocol parser sees only
    /// the latest byte after each ISR-latency window,
    /// turning intact `B1 04 00` frames into phase-shifted
    /// debris.  Task #30.
    pub fn on_sfr_read(&mut self, addr: u16, mem: &mut Memory) {
        if addr == RCREG_ADDR {
            // Pop the byte the executor just returned to the
            // firmware.  The byte already at `RCREG_ADDR` in
            // `mem` was the front of the FIFO; the executor's
            // `read_target_with_hook` captured it BEFORE
            // calling us.  Update `mem[RCREG]` so the next
            // read returns the next FIFO byte (or 0 if the
            // FIFO drains).
            self.rx_fifo.pop_front();
            self.update_rx_front_sfrs(mem);
            // RCIF tracks "FIFO non-empty".  Clear it only
            // when the FIFO is now empty.
            if self.rx_fifo.is_empty() {
                let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
                mem.write_raw(Address::from_raw(PIR1_ADDR), pir1 & !PIR1_RCIF);
            }
        }
    }

    /// React to a SW-driven SFR write at `addr` whose new
    /// post-mask value is `value`.  Reads/writes other SFRs
    /// in `mem` only when actually needed (TXREG write reads
    /// back TXSTA/SPBRG/etc. to re-arm the baud counter).
    pub fn on_sfr_write(&mut self, addr: u16, value: u8, mem: &mut Memory) {
        match addr {
            TXREG_ADDR => self.handle_txreg_write(value, mem),
            // TXSTA / RCSTA writes can change the async-enable
            // gate (TXEN, SPEN, SYNC).  If the enable goes
            // 0->1 and a TXREG byte was waiting in
            // `txreg_holding` (firmware idiom: load TXREG
            // first, then flip TXEN), kick off the TSR
            // transfer NOW -- otherwise the held byte would
            // be stuck forever.
            TXSTA_ADDR | RCSTA_ADDR => {
                if addr == RCSTA_ADDR {
                    self.handle_rcsta_write(value, mem);
                }
                self.maybe_start_held_byte(mem);
                self.recompute_txif(mem);
            }
            // SPBRG{,H} / BAUDCON only affect the baud-period
            // formula evaluated on the next TXREG load -- no
            // eager work needed.
            SPBRG_ADDR | SPBRGH_ADDR | BAUDCON_ADDR => {}
            _ => {}
        }
    }

    /// Handle the RX-side state effects of an RCSTA write.
    ///
    /// Per DS39632E §20.4.4 / DS40001303H Reg 17-2 OERR
    /// description, the silicon CREN-falling-edge contract
    /// is narrower than "reset the receiver": writing
    /// CREN=0 ONLY clears the OERR latch.  Already-buffered
    /// FIFO bytes remain readable (the firmware can drain
    /// them via RCREG reads after the recovery sequence);
    /// the receiver merely refuses to accept NEW bytes
    /// while CREN=0.  V3.1's `uart_oerr_recover` idiom
    /// (`bcf RCSTA, 4; bsf RCSTA, 4`) relies on this:
    /// falling edge clears OERR, rising edge re-arms.
    ///
    /// SPEN=0 (Serial Port Disable) is the harder reset --
    /// it disables the entire EUSART module, drains the
    /// FIFO, and clears RCREG.  Codex review of 4f7deb5
    /// HIGH: previously CREN=0 over-drained, masking the
    /// silicon stale-FIFO contract; SPEN=0 didn't drain.
    fn handle_rcsta_write(&mut self, value: u8, mem: &mut Memory) {
        if (value & RCSTA_SPEN) == 0 {
            // SPEN=0: full EUSART shutdown.  Per DS39632E
            // §20.0 "Serial Port Enable bit -- 1 = Serial
            // port enabled (configures RX/DT and TX/CK pins
            // as serial port pins); 0 = Serial port disabled
            // (held in Reset)".  Both RX and TX state
            // machines drain.
            //   RX side: FIFO + RCREG + RCIF + OERR clear.
            //   TX side: TSR busy, TSR byte, TXREG holding,
            //   and completed-TX FIFO all clear.  Without
            //   the TX-side drain, a held `txreg_holding`
            //   byte would resume mid-frame when SPEN is
            //   re-asserted, and `tick_tcy` could retire an
            //   in-flight TSR byte after the firmware
            //   thought the EUSART was off.  Codex review of
            //   4f7deb5 MEDIUM.
            self.rx_fifo.clear();
            let rcsta = mem.read_raw(Address::from_raw(RCSTA_ADDR));
            mem.write_raw(
                Address::from_raw(RCSTA_ADDR),
                rcsta & !(RCSTA_OERR | RCSTA_FERR | RCSTA_RX9D),
            );
            mem.write_raw(Address::from_raw(RCREG_ADDR), 0);
            let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
            mem.write_raw(Address::from_raw(PIR1_ADDR), pir1 & !PIR1_RCIF);
            self.tsr_busy_tcy = None;
            self.tsr_byte = None;
            self.tsr_send_break = false;
            self.txreg_holding = None;
            self.txreg_holding_send_break = false;
            self.txif_delay_tcy = 0;
            self.completed_tx_bytes.clear();
            // TSR idle -> TXSTA.TRMT = 1.  Without this,
            // an in-flight frame's TRMT=0 state would
            // survive: `tick_tcy` returns early once
            // `tsr_busy_tcy == None` and never reasserts
            // TRMT, so firmware that polls TRMT after a
            // SPEN-recovery cycle would see stale 0.  Codex
            // review of 35c2e3d MEDIUM (TX-side drain).
            set_txsta_trmt(mem, true);
            return;
        }
        if (value & RCSTA_CREN) == 0 {
            // CREN=0 with SPEN=1: clear OERR latch only.
            // FIFO + RCREG + RCIF preserved per DS
            // §20.4.4 -- firmware can still read out
            // already-buffered bytes; the receiver just
            // refuses to accept NEW bytes (gated by the
            // SPEN/CREN check in `deliver_rx_byte`).
            let rcsta = mem.read_raw(Address::from_raw(RCSTA_ADDR));
            mem.write_raw(Address::from_raw(RCSTA_ADDR), rcsta & !RCSTA_OERR);
        }
    }

    /// If the async-TX gate is on, the TSR is idle, and a
    /// byte is parked in `txreg_holding` (typical firmware
    /// idiom: write TXREG first, then enable TXEN with a BSF
    /// or MOVWF), launch the TSR transfer now.  Called from
    /// the TXSTA / RCSTA write observer.
    fn maybe_start_held_byte(&mut self, mem: &mut Memory) {
        if self.tsr_busy_tcy.is_some() {
            return;
        }
        let Some(byte) = self.txreg_holding else {
            return;
        };
        if !is_async_tx_enabled(mem) {
            return;
        }
        // Held byte transfers from TXREG to TSR.  TXREG empty
        // -> TXIF asserts via the caller's recompute_txif.
        // TSR busy -> TRMT clears.
        self.start_tsr_frame(byte, self.txreg_holding_send_break, mem);
        self.txreg_holding = None;
        self.txreg_holding_send_break = false;
        set_txsta_trmt(mem, false);
    }

    fn start_tsr_frame(&mut self, byte: u8, send_break: bool, mem: &mut Memory) {
        self.tsr_busy_tcy = Some(current_frame_tcy(mem, send_break));
        self.tsr_byte = Some(byte);
        self.tsr_send_break = send_break;
        self.txif_delay_tcy = 2;
        set_pir1_txif(mem, false);
    }

    /// Advance the EUSART by `n` Tcy, updating TXSTA.TRMT and
    /// PIR1.TXIF when the in-flight TSR shift completes.
    /// Each completed frame's byte is appended to
    /// `completed_tx_bytes` for the chain dispatcher to
    /// drain via `take_completed_tx_byte`.  Drains carry-
    /// over Tcy across multiple frame boundaries: a single
    /// big tick that crosses N frames correctly retires N
    /// bytes in TX order (the held byte chains in immediately
    /// after the prior frame drains).
    pub fn tick_tcy(&mut self, n: u32, mem: &mut Memory) {
        self.advance_txif_delay(n, mem);
        let mut remaining_tick = n;
        while remaining_tick > 0 {
            let Some(busy) = self.tsr_busy_tcy else {
                // TSR idle; no further work no matter how
                // many Tcy are left in the tick.
                return;
            };
            if remaining_tick < busy {
                self.tsr_busy_tcy = Some(busy - remaining_tick);
                return;
            }
            // TSR drains the current byte.  Emit it to the
            // completed-TX FIFO before chaining the next
            // (or going idle) -- the chain dispatcher will
            // pull it on the next execute_core_step.
            remaining_tick -= busy;
            if let Some(byte) = self.tsr_byte.take() {
                self.completed_tx_bytes.push_back(byte);
            }
            if self.tsr_send_break {
                let txsta = mem.read_raw(Address::from_raw(TXSTA_ADDR));
                mem.write_raw(Address::from_raw(TXSTA_ADDR), txsta & !TXSTA_SENDB);
                self.tsr_send_break = false;
            }
            if let Some(byte) = self.txreg_holding.take() {
                // Held byte chains into TSR; a new frame
                // begins.  TXREG empty -> TXIF asserts;
                // TSR busy -> TRMT stays 0.
                let send_break = self.txreg_holding_send_break;
                self.txreg_holding_send_break = false;
                self.start_tsr_frame(byte, send_break, mem);
                self.advance_txif_delay(remaining_tick, mem);
                self.recompute_txif(mem);
                // Loop continues -- the remaining_tick budget
                // may still cross this new frame's deadline,
                // and the next iteration will drain it.
            } else {
                // No held byte: TSR is now idle.  TRMT
                // asserts; surplus Tcy in the tick budget are
                // dropped (no work to do).
                self.tsr_busy_tcy = None;
                set_txsta_trmt(mem, true);
                self.recompute_txif(mem);
                return;
            }
        }
    }

    fn handle_txreg_write(&mut self, byte: u8, mem: &mut Memory) {
        let send_break = (mem.read_raw(Address::from_raw(TXSTA_ADDR)) & TXSTA_SENDB) != 0;
        // The transmitter must be enabled for the frame to
        // start shifting.  If disabled, the byte still loads
        // into TXREG (datasheet behaviour: TXREG is just a
        // memory-mapped latch), but no TSR transfer happens
        // and TRMT/TXIF stay where they are.  The firmware
        // idiom is to enable TXEN *after* loading TXREG to
        // avoid a partial first-bit on the line.
        if !is_async_tx_enabled(mem) {
            // TXREG is full now; TXIF=0 (TXREG holds data,
            // not yet transferred).  But the gate is also
            // off, so the recompute keeps TXIF cleared.
            self.txreg_holding = Some(byte);
            self.txreg_holding_send_break = send_break;
            self.recompute_txif(mem);
            return;
        }

        if self.tsr_busy_tcy.is_none() {
            // TSR idle: immediate TXREG -> TSR transfer.
            // TXREG is empty; TXIF asserts (gate is on).
            // TSR is busy; TRMT clears.
            self.start_tsr_frame(byte, send_break, mem);
            self.txreg_holding = None;
            self.txreg_holding_send_break = false;
            set_txsta_trmt(mem, false);
            self.recompute_txif(mem);
        } else {
            // TSR busy: hold byte in TXREG, wait for TSR
            // drain.  TXIF clears (TXREG holds data).
            self.txreg_holding = Some(byte);
            self.txreg_holding_send_break = send_break;
            set_txsta_trmt(mem, false);
            self.recompute_txif(mem);
        }
    }

    /// Reassert PIR1.TXIF based on (TXEN ∧ SPEN ∧ ¬SYNC) ∧
    /// (TXREG empty), per DS40001303H §17.4.1.5.  The
    /// "TXIF becomes valid in the second instruction cycle
    /// following the load" delay called out in the datasheet
    /// is *not* modelled here -- a Phase-2 fidelity gap that
    /// the firmware idiom (poll TXIF in a tight loop) is not
    /// sensitive to.  Phase 4 dual-run will surface any
    /// firmware that depends on the 1-Tcy delay.
    fn recompute_txif(&mut self, mem: &mut Memory) {
        let txreg_empty = self.txreg_holding.is_none();
        let txif_should_be = is_async_tx_enabled(mem) && txreg_empty;
        if txif_should_be {
            if self.txif_delay_tcy == 0
                && (mem.read_raw(Address::from_raw(PIR1_ADDR)) & PIR1_TXIF) == 0
            {
                self.txif_delay_tcy = 2;
            }
            if self.txif_delay_tcy == 0 {
                set_pir1_txif(mem, true);
            } else {
                set_pir1_txif(mem, false);
            }
        } else {
            self.txif_delay_tcy = 0;
            set_pir1_txif(mem, false);
        }
    }

    fn advance_txif_delay(&mut self, n: u32, mem: &mut Memory) {
        if self.txif_delay_tcy == 0 {
            return;
        }
        let n = n.min(u8::MAX as u32) as u8;
        if n < self.txif_delay_tcy {
            self.txif_delay_tcy -= n;
            return;
        }
        self.txif_delay_tcy = 0;
        if is_async_tx_enabled(mem) && self.txreg_holding.is_none() {
            set_pir1_txif(mem, true);
        }
    }
}

/// Current frame width in Tcy, given the live SFR state
/// (TX9 selects the 9-bit data path, adding one bit to the
/// 10-bit start+8+stop total).
fn current_frame_tcy(mem: &Memory, send_break: bool) -> u32 {
    let period = current_baud_bit_period_tcy(mem);
    let txsta = mem.read_raw(Address::from_raw(TXSTA_ADDR));
    let frame_bits = if send_break {
        13u32
    } else if (txsta & TXSTA_TX9) != 0 {
        11u32
    } else {
        10u32
    };
    period.saturating_mul(frame_bits)
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

    // Datasheet formula is in *FOSC* terms; convert to Tcy
    // by dividing by 4 (Tcy = 4 FOSC cycles).  Resulting
    // factors in Tcy: {16, 4, 4, 1} for (BRGH, BRG16) ∈
    // {(0,0), (1,0), (0,1), (1,1)}.
    let (divisor_factor_tcy, n) = match (brg16, brgh) {
        (false, false) => (16u32, spbrg),
        (false, true) => (4u32, spbrg),
        (true, false) => (4u32, (spbrgh << 8) | spbrg),
        (true, true) => (1u32, (spbrgh << 8) | spbrg),
    };
    // bit_period_tcy = factor_tcy × (n + 1).  Clamp to 1
    // Tcy/bit so a 0-divisor firmware bug doesn't deadlock
    // the model -- the firmware then sees a degenerate but
    // making-progress baud generator.
    divisor_factor_tcy.saturating_mul(n + 1).max(1)
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
    (rcsta & RCSTA_SPEN) != 0 && (txsta & TXSTA_TXEN) != 0 && (txsta & TXSTA_SYNC) == 0
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fresh_mem() -> Memory {
        Memory::new(Variant::Pic18F25K20)
    }

    /// Drive the EUSART into the "async TX enabled" config so
    /// helpers that gate on TXEN/SPEN/SYNC actually start the
    /// state machine.
    fn enable_async_tx(mem: &mut Memory) {
        mem.write_raw(Address::from_raw(RCSTA_ADDR), RCSTA_SPEN);
        // TXEN=1, TRMT=1 (POR-correct before any TXREG load).
        mem.write_raw(Address::from_raw(TXSTA_ADDR), TXSTA_TXEN | TXSTA_TRMT);
    }

    /// V1.71 boot config: SPBRG=5, BRGH=0, BRG16=0 -> 1 bit =
    /// 16 × (5+1) = 96 Tcy at the K20's 3 MIPS Fcy.  31250
    /// baud: 3e6 / 31250 = 96 Tcy/bit ✓.
    #[test]
    fn baud_period_v171_31250_baud() {
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(SPBRG_ADDR), 5);
        mem.write_raw(Address::from_raw(TXSTA_ADDR), 0x20); // TXEN
        mem.write_raw(Address::from_raw(BAUDCON_ADDR), 0x40); // RCIDL, BRG16=0
        assert_eq!(current_baud_bit_period_tcy(&mem), 96);
    }

    /// BRGH=1, BRG16=0 -> 1 bit = 4 × (n+1) Tcy.
    #[test]
    fn baud_period_brgh_high() {
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(SPBRG_ADDR), 25);
        mem.write_raw(Address::from_raw(TXSTA_ADDR), 0x24); // TXEN | BRGH
        mem.write_raw(Address::from_raw(BAUDCON_ADDR), 0);
        assert_eq!(current_baud_bit_period_tcy(&mem), 4 * 26);
    }

    /// BRG16=1, BRGH=0 -> factor=4 in Tcy.  n = SPBRGH:SPBRG.
    #[test]
    fn baud_period_brg16_uses_spbrgh() {
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(SPBRG_ADDR), 0x20);
        mem.write_raw(Address::from_raw(SPBRGH_ADDR), 0x01);
        mem.write_raw(Address::from_raw(TXSTA_ADDR), 0x20);
        mem.write_raw(Address::from_raw(BAUDCON_ADDR), 0x08); // BRG16
        // n = 0x0120 = 288;  factor_tcy = 4 -> 4 × 289 = 1156.
        assert_eq!(current_baud_bit_period_tcy(&mem), 4 * 289);
    }

    /// SPBRG=0, BRG16=1, BRGH=1 -> factor_tcy=1, n+1=1 -> 1 Tcy/bit.
    #[test]
    fn baud_period_minimum_is_one_tcy_per_bit() {
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(TXSTA_ADDR), 0x24);
        mem.write_raw(Address::from_raw(BAUDCON_ADDR), 0x08);
        assert_eq!(current_baud_bit_period_tcy(&mem), 1);
    }

    /// V1.71 boot: TXREG=0x55 with TX enabled.  TSR is idle, so
    /// the byte transfers immediately, TRMT clears, TXIF stays 1
    /// (TXREG empty).  Frame = 10 × 96 = 960 Tcy.  After 960 Tcy,
    /// TRMT reasserts.
    #[test]
    fn txreg_write_starts_frame_idle_tsr_keeps_txif_high() {
        let mut eusart = Eusart::new(Variant::Pic18F25K20);
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(SPBRG_ADDR), 5);
        mem.write_raw(Address::from_raw(BAUDCON_ADDR), 0x40);
        enable_async_tx(&mut mem);

        // TXREG write into idle TSR -- TXREG transfers
        // immediately, so TXREG becomes empty; TXIF becomes
        // valid two Tcy later.
        eusart.on_sfr_write(TXREG_ADDR, 0x55, &mut mem);
        let txsta = mem.read_raw(Address::from_raw(TXSTA_ADDR));
        let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
        assert_eq!(txsta & TXSTA_TRMT, 0, "TRMT must clear once TSR loads");
        assert_eq!(pir1 & PIR1_TXIF, 0, "TXIF delay starts low");
        eusart.tick_tcy(2, &mut mem);
        let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
        assert_eq!(
            pir1 & PIR1_TXIF,
            PIR1_TXIF,
            "TXIF asserts on the second Tcy after TXREG -> TSR"
        );

        // Mid-frame: TRMT still 0.
        eusart.tick_tcy(498, &mut mem);
        let txsta = mem.read_raw(Address::from_raw(TXSTA_ADDR));
        assert_eq!(txsta & TXSTA_TRMT, 0, "TRMT must stay 0 mid-frame");

        // Past the 960-Tcy boundary: TRMT reasserts.
        eusart.tick_tcy(500, &mut mem); // total 1000 >= 960
        let txsta = mem.read_raw(Address::from_raw(TXSTA_ADDR));
        let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
        assert_eq!(
            txsta & TXSTA_TRMT,
            TXSTA_TRMT,
            "TRMT must reassert post-frame"
        );
        assert_eq!(
            pir1 & PIR1_TXIF,
            PIR1_TXIF,
            "TXIF stays 1 once TXREG drained"
        );
    }

    /// Back-to-back writes: write byte A (TSR loads, TXREG
    /// empty); write byte B (TSR busy, TXREG holds, TXIF=0);
    /// after 960 Tcy TSR drains, B transfers from TXREG to
    /// TSR (TXIF=1), TRMT stays 0; after 1920 Tcy total TSR
    /// drains for B, TRMT=1.
    #[test]
    fn back_to_back_txreg_writes_chain_through_tsr() {
        let mut eusart = Eusart::new(Variant::Pic18F25K20);
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(SPBRG_ADDR), 5);
        mem.write_raw(Address::from_raw(BAUDCON_ADDR), 0x40);
        enable_async_tx(&mut mem);

        eusart.on_sfr_write(TXREG_ADDR, 0xAA, &mut mem);
        // TXREG empty after immediate transfer -> TXIF after
        // the documented two-Tcy validity delay.
        assert_eq!(mem.read_raw(Address::from_raw(PIR1_ADDR)) & PIR1_TXIF, 0);
        eusart.tick_tcy(2, &mut mem);
        let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
        assert_eq!(pir1 & PIR1_TXIF, PIR1_TXIF);

        // Second write while TSR is shifting first byte.
        eusart.on_sfr_write(TXREG_ADDR, 0xBB, &mut mem);
        let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
        assert_eq!(
            pir1 & PIR1_TXIF,
            0,
            "TXIF must clear when TXREG holds queued byte"
        );

        // After first frame drains: B chains into TSR; TXREG
        // is empty again -> TXIF asserts; TRMT stays 0.
        eusart.tick_tcy(960, &mut mem);
        let txsta = mem.read_raw(Address::from_raw(TXSTA_ADDR));
        let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
        assert_eq!(txsta & TXSTA_TRMT, 0, "TRMT stays 0 with B in TSR");
        assert_eq!(pir1 & PIR1_TXIF, PIR1_TXIF, "TXIF reasserts after chain");

        // After second frame drains.
        eusart.tick_tcy(960, &mut mem);
        let txsta = mem.read_raw(Address::from_raw(TXSTA_ADDR));
        assert_eq!(txsta & TXSTA_TRMT, TXSTA_TRMT);
    }

    /// TXREG write while TX disabled (TXEN=0): byte loads into
    /// TXREG holding latch but TSR doesn't start; TXIF stays 0
    /// because the gate is off.
    #[test]
    fn txreg_write_without_txen_holds_byte_no_frame() {
        let mut eusart = Eusart::new(Variant::Pic18F25K20);
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(SPBRG_ADDR), 5);
        mem.write_raw(Address::from_raw(BAUDCON_ADDR), 0x40);
        // SPEN=1 but TXEN=0 -> async path disabled.
        mem.write_raw(Address::from_raw(RCSTA_ADDR), RCSTA_SPEN);

        eusart.on_sfr_write(TXREG_ADDR, 0x42, &mut mem);
        let txsta = mem.read_raw(Address::from_raw(TXSTA_ADDR));
        let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
        assert_eq!(
            txsta & TXSTA_TRMT,
            0,
            "TRMT POR is 0 in this synthetic mem; not changed"
        );
        assert_eq!(pir1 & PIR1_TXIF, 0, "TXIF must be 0 with async-tx gate off");

        // No frame should drain even after many Tcy.
        eusart.tick_tcy(10_000, &mut mem);
        let txsta = mem.read_raw(Address::from_raw(TXSTA_ADDR));
        assert_eq!(txsta & TXSTA_TRMT, 0, "no TSR shift -> TRMT unchanged");
    }

    /// Enabling TX (TXEN 0->1) with TXREG empty must assert
    /// TXIF without a TXREG write -- the hardware fires TXIF
    /// as soon as the transmitter is enabled (DS §17.4.1.5).
    #[test]
    fn enabling_txen_with_empty_txreg_asserts_txif() {
        let mut eusart = Eusart::new(Variant::Pic18F25K20);
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(RCSTA_ADDR), RCSTA_SPEN);
        // TXIF should still be 0 with TXEN=0.
        let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
        assert_eq!(pir1 & PIR1_TXIF, 0);

        // Firmware writes TXSTA to enable TXEN.  The peripheral
        // observes that change and starts the two-Tcy TXIF
        // validity delay.
        mem.write_raw(Address::from_raw(TXSTA_ADDR), TXSTA_TXEN | TXSTA_TRMT);
        eusart.on_sfr_write(TXSTA_ADDR, TXSTA_TXEN | TXSTA_TRMT, &mut mem);
        assert_eq!(mem.read_raw(Address::from_raw(PIR1_ADDR)) & PIR1_TXIF, 0);
        eusart.tick_tcy(2, &mut mem);
        let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
        assert_eq!(
            pir1 & PIR1_TXIF,
            PIR1_TXIF,
            "TXIF must assert when TXEN goes 0->1 with empty TXREG"
        );
    }

    /// TX9=1: frame is 11 bits, not 10.  Frame Tcy = 11 × 96 = 1056.
    #[test]
    fn tx9_extends_frame_to_11_bits() {
        let mut eusart = Eusart::new(Variant::Pic18F25K20);
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(SPBRG_ADDR), 5);
        mem.write_raw(Address::from_raw(BAUDCON_ADDR), 0x40);
        // TXEN | TX9 | TRMT.
        mem.write_raw(Address::from_raw(RCSTA_ADDR), RCSTA_SPEN);
        mem.write_raw(
            Address::from_raw(TXSTA_ADDR),
            TXSTA_TXEN | TXSTA_TX9 | TXSTA_TRMT,
        );
        eusart.on_sfr_write(TXREG_ADDR, 0x55, &mut mem);

        // Tick exactly 960 Tcy (10-bit boundary): TRMT must
        // still be 0 because the frame is 11 bits.
        eusart.tick_tcy(960, &mut mem);
        let txsta = mem.read_raw(Address::from_raw(TXSTA_ADDR));
        assert_eq!(
            txsta & TXSTA_TRMT,
            0,
            "TX9=1 keeps TRMT low past 10-bit boundary"
        );

        // Tick to 1056 (11-bit boundary): TRMT reasserts.
        eusart.tick_tcy(96, &mut mem);
        let txsta = mem.read_raw(Address::from_raw(TXSTA_ADDR));
        assert_eq!(
            txsta & TXSTA_TRMT,
            TXSTA_TRMT,
            "TX9=1 frame completes at 11-bit boundary (1056 Tcy)"
        );
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
        assert!(!is_async_tx_enabled(&mem));
        mem.write_raw(Address::from_raw(RCSTA_ADDR), RCSTA_SPEN);
        assert!(!is_async_tx_enabled(&mem));
        mem.write_raw(Address::from_raw(TXSTA_ADDR), TXSTA_TXEN);
        assert!(is_async_tx_enabled(&mem));
        mem.write_raw(Address::from_raw(TXSTA_ADDR), TXSTA_TXEN | TXSTA_SYNC);
        assert!(!is_async_tx_enabled(&mem));
    }

    /// Firmware idiom: load TXREG first, then enable TXEN.
    /// The held byte must transfer to TSR when the gate flips
    /// 0->1 -- without the on_sfr_write hook on TXSTA reaching
    /// for `maybe_start_held_byte`, the byte would be stuck
    /// forever (TSR idle, no further tick_tcy ever fires).
    #[test]
    fn enabling_txen_after_txreg_write_starts_held_byte() {
        let mut eusart = Eusart::new(Variant::Pic18F25K20);
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(SPBRG_ADDR), 5);
        mem.write_raw(Address::from_raw(BAUDCON_ADDR), 0x40);
        // SPEN=1, TXEN=0 -> async path disabled.
        mem.write_raw(Address::from_raw(RCSTA_ADDR), RCSTA_SPEN);

        // Write TXREG while disabled.  Byte holds; TXIF=0.
        eusart.on_sfr_write(TXREG_ADDR, 0x42, &mut mem);
        assert!(eusart.txreg_holding.is_some());
        assert!(eusart.tsr_busy_tcy.is_none());

        // Now firmware enables TXEN.  Held byte should
        // transfer to TSR; TRMT clears; TXIF asserts after
        // the documented two-Tcy validity delay.
        let new_txsta = TXSTA_TXEN | TXSTA_TRMT;
        mem.write_raw(Address::from_raw(TXSTA_ADDR), new_txsta);
        eusart.on_sfr_write(TXSTA_ADDR, new_txsta, &mut mem);
        assert!(
            eusart.tsr_busy_tcy.is_some(),
            "held byte must move to TSR when TXEN goes 0->1"
        );
        assert!(eusart.txreg_holding.is_none());
        let txsta = mem.read_raw(Address::from_raw(TXSTA_ADDR));
        let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
        assert_eq!(
            txsta & TXSTA_TRMT,
            0,
            "TRMT must clear once TSR loads (TXSTA=0x{txsta:02X})"
        );
        assert_eq!(pir1 & PIR1_TXIF, 0, "TXIF delay starts low");
        eusart.tick_tcy(2, &mut mem);
        assert_eq!(
            mem.read_raw(Address::from_raw(PIR1_ADDR)) & PIR1_TXIF,
            PIR1_TXIF,
            "TXIF must assert two Tcy after transfer"
        );

        // After 960 Tcy the frame drains -> TRMT reasserts.
        eusart.tick_tcy(958, &mut mem);
        let txsta = mem.read_raw(Address::from_raw(TXSTA_ADDR));
        assert_eq!(txsta & TXSTA_TRMT, TXSTA_TRMT);
    }

    /// Single tick that exceeds the current frame *and* drains
    /// a held byte's frame must consume the chained Tcy budget,
    /// not start the held frame from full.  (Phase-2 unit
    /// tests typically tick 1 Tcy at a time so this rarely
    /// matters in practice, but the LOW codex finding flagged
    /// the surplus-drop as a fidelity gap in larger ticks.)
    #[test]
    fn tick_carries_surplus_tcy_across_chained_frames() {
        let mut eusart = Eusart::new(Variant::Pic18F25K20);
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(SPBRG_ADDR), 5);
        mem.write_raw(Address::from_raw(BAUDCON_ADDR), 0x40);
        enable_async_tx(&mut mem);

        eusart.on_sfr_write(TXREG_ADDR, 0xAA, &mut mem); // -> TSR
        eusart.on_sfr_write(TXREG_ADDR, 0xBB, &mut mem); // held

        // First frame = 960 Tcy; second frame = 960 Tcy; total
        // 1920 Tcy.  Tick exactly 1920 -> both should drain.
        // The buggy version would consume 960 (drain frame 1),
        // start frame 2 with full 960 budget, then have 0 Tcy
        // left -> frame 2 stays in flight -> TRMT still 0.
        eusart.tick_tcy(1920, &mut mem);
        let txsta = mem.read_raw(Address::from_raw(TXSTA_ADDR));
        assert_eq!(
            txsta & TXSTA_TRMT,
            TXSTA_TRMT,
            "Both frames must drain in a single 1920-Tcy tick"
        );
        let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
        assert_eq!(pir1 & PIR1_TXIF, PIR1_TXIF);
        assert!(eusart.tsr_busy_tcy.is_none());
        assert!(eusart.txreg_holding.is_none());
    }

    /// Frame completion appends the transmitted byte to
    /// the completed-TX FIFO; the chain dispatcher drains
    /// it via `take_completed_tx_byte`.
    #[test]
    fn frame_completion_appends_byte_to_completed_tx_fifo() {
        let mut eusart = Eusart::new(Variant::Pic18F25K20);
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(SPBRG_ADDR), 5);
        mem.write_raw(Address::from_raw(BAUDCON_ADDR), 0x40);
        enable_async_tx(&mut mem);
        eusart.on_sfr_write(TXREG_ADDR, 0xAA, &mut mem);
        // Mid-frame: nothing in FIFO yet.
        eusart.tick_tcy(500, &mut mem);
        assert!(eusart.take_completed_tx_byte().is_none());
        // Frame completes (10 bits × 96 Tcy = 960; we've
        // ticked 500, need 460 more).
        eusart.tick_tcy(500, &mut mem);
        assert_eq!(eusart.take_completed_tx_byte(), Some(0xAA));
        // FIFO empty after drain.
        assert!(eusart.take_completed_tx_byte().is_none());
    }

    /// Chained TX (back-to-back writes) appends both bytes
    /// to the FIFO in TX order.
    #[test]
    fn chained_tx_appends_in_order() {
        let mut eusart = Eusart::new(Variant::Pic18F25K20);
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(SPBRG_ADDR), 5);
        mem.write_raw(Address::from_raw(BAUDCON_ADDR), 0x40);
        enable_async_tx(&mut mem);
        eusart.on_sfr_write(TXREG_ADDR, 0x11, &mut mem);
        eusart.on_sfr_write(TXREG_ADDR, 0x22, &mut mem);
        // Tick past both frames.
        eusart.tick_tcy(2_000, &mut mem);
        assert_eq!(eusart.take_completed_tx_byte(), Some(0x11));
        assert_eq!(eusart.take_completed_tx_byte(), Some(0x22));
        assert!(eusart.take_completed_tx_byte().is_none());
    }

    /// `deliver_rx_byte` loads RCREG and asserts RCIF when
    /// SPEN AND CREN are set; silently drops otherwise.
    #[test]
    fn deliver_rx_byte_asserts_rcif_when_spen_and_cren_set() {
        let mut eusart = Eusart::new(Variant::Pic18F25K20);
        let mut mem = fresh_mem();
        // SPEN | CREN.
        const RCSTA_CREN: u8 = 1 << 4;
        mem.write_raw(Address::from_raw(RCSTA_ADDR), RCSTA_SPEN | RCSTA_CREN);
        eusart.deliver_rx_byte(0x77, &mut mem);
        assert_eq!(mem.read_raw(Address::from_raw(RCREG_ADDR)), 0x77);
        let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
        assert_eq!(pir1 & PIR1_RCIF, PIR1_RCIF);
    }

    #[test]
    fn deliver_rx_byte_drops_when_spen_clear() {
        let mut eusart = Eusart::new(Variant::Pic18F25K20);
        let mut mem = fresh_mem();
        // CREN=1 but SPEN=0.
        const RCSTA_CREN: u8 = 1 << 4;
        mem.write_raw(Address::from_raw(RCSTA_ADDR), RCSTA_CREN);
        eusart.deliver_rx_byte(0x77, &mut mem);
        assert_eq!(mem.read_raw(Address::from_raw(RCREG_ADDR)), 0);
        assert_eq!(mem.read_raw(Address::from_raw(PIR1_ADDR)) & PIR1_RCIF, 0);
    }

    #[test]
    fn deliver_rx_byte_drops_when_cren_clear() {
        let mut eusart = Eusart::new(Variant::Pic18F25K20);
        let mut mem = fresh_mem();
        // SPEN=1 but CREN=0 (POR default for CREN).
        mem.write_raw(Address::from_raw(RCSTA_ADDR), RCSTA_SPEN);
        eusart.deliver_rx_byte(0x88, &mut mem);
        assert_eq!(mem.read_raw(Address::from_raw(RCREG_ADDR)), 0);
        assert_eq!(mem.read_raw(Address::from_raw(PIR1_ADDR)) & PIR1_RCIF, 0);
    }

    /// Task #30: reading RCREG must clear RCIF.  DS39632E
    /// Reg 9-4 (PIR1) bit 5: "RCIF: EUSART Receive Interrupt
    /// Flag bit -- 1 = the EUSART receive buffer, RCREG, is
    /// full (cleared when RCREG is read); 0 = the EUSART
    /// receive buffer is empty."  Our 1-byte model is always
    /// "FIFO now empty" after a read.  Without this clear,
    /// V3.1's level-triggered IRQ dispatcher re-fires on the
    /// same byte and the ISR's frame parser re-processes it,
    /// completing bogus 3-byte frames that the firmware
    /// rejects.
    #[test]
    fn rcreg_read_clears_rcif() {
        let mut eusart = Eusart::new(Variant::Pic18F25K20);
        let mut mem = fresh_mem();
        const RCSTA_CREN: u8 = 1 << 4;
        mem.write_raw(Address::from_raw(RCSTA_ADDR), RCSTA_SPEN | RCSTA_CREN);
        eusart.deliver_rx_byte(0xAB, &mut mem);
        assert_eq!(
            mem.read_raw(Address::from_raw(PIR1_ADDR)) & PIR1_RCIF,
            PIR1_RCIF,
            "pre: RCIF asserted by deliver"
        );
        // Simulate an executor read by invoking on_sfr_read
        // at RCREG's address.  (Memory side: the byte was
        // already read by the executor; on_sfr_read just
        // updates collateral state.)
        eusart.on_sfr_read(RCREG_ADDR, &mut mem);
        assert_eq!(
            mem.read_raw(Address::from_raw(PIR1_ADDR)) & PIR1_RCIF,
            0,
            "post: RCIF cleared by RCREG read"
        );
    }

    /// 2-deep RX FIFO contract (DS39632E §20.0): two
    /// consecutive `deliver_rx_byte` calls without an
    /// intervening RCREG read leave both bytes available;
    /// the first read returns byte #1, the second returns
    /// byte #2.  RCIF stays asserted while the FIFO is
    /// non-empty; clears on the read that drains it.
    /// Task #30 root-cause -- without this depth, V3.1's
    /// chain-protocol parser sees only the latest byte.
    #[test]
    fn rx_fifo_holds_two_bytes_in_order() {
        let mut eusart = Eusart::new(Variant::Pic18F25K20);
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(RCSTA_ADDR), RCSTA_SPEN | RCSTA_CREN);
        eusart.deliver_rx_byte(0xB1, &mut mem);
        eusart.deliver_rx_byte(0x04, &mut mem);
        // RCREG holds the OLDEST (front) byte.
        assert_eq!(
            mem.read_raw(Address::from_raw(RCREG_ADDR)),
            0xB1,
            "RCREG must show the oldest FIFO byte"
        );
        // RCIF set (FIFO non-empty).
        assert_eq!(
            mem.read_raw(Address::from_raw(PIR1_ADDR)) & PIR1_RCIF,
            PIR1_RCIF
        );
        // First read: pop 0xB1; RCREG shows next (0x04); RCIF stays.
        eusart.on_sfr_read(RCREG_ADDR, &mut mem);
        assert_eq!(
            mem.read_raw(Address::from_raw(RCREG_ADDR)),
            0x04,
            "after popping 0xB1, RCREG must show next byte 0x04"
        );
        assert_eq!(
            mem.read_raw(Address::from_raw(PIR1_ADDR)) & PIR1_RCIF,
            PIR1_RCIF,
            "RCIF stays asserted while FIFO non-empty"
        );
        // Second read: pop 0x04; FIFO empty; RCIF clears.
        eusart.on_sfr_read(RCREG_ADDR, &mut mem);
        assert_eq!(
            mem.read_raw(Address::from_raw(PIR1_ADDR)) & PIR1_RCIF,
            0,
            "RCIF clears when FIFO drains"
        );
    }

    /// A third byte arriving while the FIFO is full latches
    /// `RCSTA.OERR` and is dropped (DS §20.4.4 / Reg 9-4).
    /// Firmware clears OERR by writing `RCSTA.CREN=0`.
    #[test]
    fn rx_fifo_third_byte_sets_oerr_and_is_dropped() {
        let mut eusart = Eusart::new(Variant::Pic18F25K20);
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(RCSTA_ADDR), RCSTA_SPEN | RCSTA_CREN);
        eusart.deliver_rx_byte(0x11, &mut mem);
        eusart.deliver_rx_byte(0x22, &mut mem);
        // Third byte: dropped, OERR latched.
        eusart.deliver_rx_byte(0x33, &mut mem);
        assert_eq!(
            mem.read_raw(Address::from_raw(RCSTA_ADDR)) & RCSTA_OERR,
            RCSTA_OERR,
            "third byte while FIFO full must latch OERR"
        );
        // FIFO still has the original two bytes; the dropped
        // 0x33 never appears.
        eusart.on_sfr_read(RCREG_ADDR, &mut mem); // pop 0x11
        assert_eq!(
            mem.read_raw(Address::from_raw(RCREG_ADDR)),
            0x22,
            "after popping 0x11, RCREG shows 0x22 (NOT 0x33)"
        );
        eusart.on_sfr_read(RCREG_ADDR, &mut mem); // pop 0x22
        assert_eq!(
            mem.read_raw(Address::from_raw(RCREG_ADDR)),
            0,
            "FIFO empty -- dropped 0x33 was lost"
        );
    }

    /// V3.1's `uart_oerr_recover` writes `RCSTA.CREN=0` to
    /// clear OERR, then writes CREN=1 to re-arm the
    /// receiver.  Per DS39632E §20.4.4 / DS40001303H Reg
    /// 17-2 OERR description, the CREN-falling-edge ONLY
    /// clears the OERR latch -- the FIFO + RCREG + RCIF are
    /// preserved (firmware can still read out already-
    /// buffered bytes).  Codex review of 4f7deb5 HIGH:
    /// the prior commit over-drained, masking the silicon
    /// stale-FIFO contract.
    #[test]
    fn rcsta_cren_falling_edge_clears_oerr_only_preserving_fifo() {
        let mut eusart = Eusart::new(Variant::Pic18F25K20);
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(RCSTA_ADDR), RCSTA_SPEN | RCSTA_CREN);
        eusart.deliver_rx_byte(0xAA, &mut mem);
        eusart.deliver_rx_byte(0xBB, &mut mem);
        eusart.deliver_rx_byte(0xCC, &mut mem); // overflow -> OERR set
        assert_eq!(
            mem.read_raw(Address::from_raw(RCSTA_ADDR)) & RCSTA_OERR,
            RCSTA_OERR
        );
        // Firmware: bcf RCSTA, 4 (clear CREN).
        let rcsta = mem.read_raw(Address::from_raw(RCSTA_ADDR));
        let new_rcsta = rcsta & !RCSTA_CREN;
        mem.write_raw(Address::from_raw(RCSTA_ADDR), new_rcsta);
        eusart.on_sfr_write(RCSTA_ADDR, new_rcsta, &mut mem);
        // OERR cleared.
        assert_eq!(
            mem.read_raw(Address::from_raw(RCSTA_ADDR)) & RCSTA_OERR,
            0,
            "CREN=0 must clear OERR"
        );
        // FIFO + RCREG + RCIF preserved -- firmware can
        // still drain the already-buffered bytes after the
        // recovery sequence.
        assert_eq!(
            mem.read_raw(Address::from_raw(RCREG_ADDR)),
            0xAA,
            "RCREG preserves the front FIFO byte across CREN=0"
        );
        assert_eq!(
            mem.read_raw(Address::from_raw(PIR1_ADDR)) & PIR1_RCIF,
            PIR1_RCIF,
            "RCIF stays asserted -- FIFO non-empty"
        );
        // Drain the FIFO via reads.
        eusart.on_sfr_read(RCREG_ADDR, &mut mem); // pop 0xAA
        assert_eq!(
            mem.read_raw(Address::from_raw(RCREG_ADDR)),
            0xBB,
            "second FIFO byte still readable"
        );
        eusart.on_sfr_read(RCREG_ADDR, &mut mem); // pop 0xBB
        assert_eq!(
            mem.read_raw(Address::from_raw(PIR1_ADDR)) & PIR1_RCIF,
            0,
            "RCIF clears when FIFO empties"
        );
    }

    /// Codex review of 4f7deb5 MEDIUM: once OERR is set,
    /// the silicon refuses to accept further bytes until
    /// firmware clears OERR (via CREN=0).  Even reading
    /// RCREG to free a FIFO slot is NOT enough.
    #[test]
    fn oerr_blocks_rx_until_cren_toggle() {
        let mut eusart = Eusart::new(Variant::Pic18F25K20);
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(RCSTA_ADDR), RCSTA_SPEN | RCSTA_CREN);
        eusart.deliver_rx_byte(0x11, &mut mem);
        eusart.deliver_rx_byte(0x22, &mut mem);
        eusart.deliver_rx_byte(0x33, &mut mem); // -> OERR set, dropped
        assert_eq!(
            mem.read_raw(Address::from_raw(RCSTA_ADDR)) & RCSTA_OERR,
            RCSTA_OERR
        );
        // Firmware reads RCREG to free a FIFO slot.
        eusart.on_sfr_read(RCREG_ADDR, &mut mem); // pop 0x11
        assert_eq!(
            mem.read_raw(Address::from_raw(RCSTA_ADDR)) & RCSTA_OERR,
            RCSTA_OERR,
            "OERR still latched after RCREG drain"
        );
        // New byte arrives while OERR set: silicon refuses.
        eusart.deliver_rx_byte(0x44, &mut mem);
        // FIFO should still have only 0x22 (the original
        // second byte); 0x44 was rejected.
        assert_eq!(
            mem.read_raw(Address::from_raw(RCREG_ADDR)),
            0x22,
            "0x44 must be rejected while OERR latched"
        );
        eusart.on_sfr_read(RCREG_ADDR, &mut mem); // pop 0x22
        assert_eq!(
            mem.read_raw(Address::from_raw(PIR1_ADDR)) & PIR1_RCIF,
            0,
            "FIFO drained: only original 0x11/0x22 ever landed"
        );
        // Now firmware does the recovery: CREN=0 then CREN=1.
        let rcsta = mem.read_raw(Address::from_raw(RCSTA_ADDR));
        mem.write_raw(Address::from_raw(RCSTA_ADDR), rcsta & !RCSTA_CREN);
        eusart.on_sfr_write(RCSTA_ADDR, rcsta & !RCSTA_CREN, &mut mem);
        let rcsta = mem.read_raw(Address::from_raw(RCSTA_ADDR));
        mem.write_raw(Address::from_raw(RCSTA_ADDR), rcsta | RCSTA_CREN);
        eusart.on_sfr_write(RCSTA_ADDR, rcsta | RCSTA_CREN, &mut mem);
        // Receiver re-armed: new bytes accepted.
        eusart.deliver_rx_byte(0x55, &mut mem);
        assert_eq!(
            mem.read_raw(Address::from_raw(RCREG_ADDR)),
            0x55,
            "after CREN-toggle recovery, new bytes accepted"
        );
    }

    /// SPEN=0 (Serial Port Disable) is the harder reset --
    /// it shuts down the EUSART entirely, draining BOTH
    /// the RX FIFO and the TX-side state machine (TSR
    /// busy, TXREG holding, completed-TX queue).  Per
    /// DS39632E §20.0 SPEN description: "0 = Serial port
    /// disabled (held in Reset)".  Distinct from CREN=0
    /// which only clears OERR.  Codex review of 35c2e3d
    /// MEDIUM extended this to cover the TX side.
    #[test]
    fn rcsta_spen_falling_edge_drains_fifo_and_clears_state() {
        let mut eusart = Eusart::new(Variant::Pic18F25K20);
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(RCSTA_ADDR), RCSTA_SPEN | RCSTA_CREN);
        eusart.deliver_rx_byte(0xAA, &mut mem);
        eusart.deliver_rx_byte(0xBB, &mut mem);
        eusart.deliver_rx_byte(0xCC, &mut mem); // OERR set
        // Push some TX state too: a frame in the TSR + a
        // held byte queued for after + a previously-
        // completed byte sitting in the TX history (a
        // chain dispatcher hasn't yet drained).
        mem.write_raw(Address::from_raw(TXSTA_ADDR), TXSTA_TXEN | TXSTA_TRMT);
        eusart.on_sfr_write(TXSTA_ADDR, TXSTA_TXEN | TXSTA_TRMT, &mut mem);
        eusart.on_sfr_write(TXREG_ADDR, 0x55, &mut mem); // -> TSR
        eusart.on_sfr_write(TXREG_ADDR, 0x77, &mut mem); // -> txreg_holding
        eusart.push_completed_tx_byte_for_test(0x99); // queue a finished byte
        assert!(eusart.tsr_busy_tcy.is_some());
        assert!(eusart.tsr_byte.is_some());
        assert!(eusart.txreg_holding.is_some());
        // TRMT was cleared when TXREG -> TSR launched the
        // first frame.
        let txsta_pre = mem.read_raw(Address::from_raw(TXSTA_ADDR));
        assert_eq!(
            txsta_pre & TXSTA_TRMT,
            0,
            "pre: TRMT cleared while TSR busy"
        );
        // Firmware: bcf RCSTA, 7 (clear SPEN).
        let rcsta = mem.read_raw(Address::from_raw(RCSTA_ADDR));
        let new_rcsta = rcsta & !RCSTA_SPEN;
        mem.write_raw(Address::from_raw(RCSTA_ADDR), new_rcsta);
        eusart.on_sfr_write(RCSTA_ADDR, new_rcsta, &mut mem);
        // Full shutdown: RX side clears.
        assert_eq!(mem.read_raw(Address::from_raw(RCSTA_ADDR)) & RCSTA_OERR, 0);
        assert_eq!(mem.read_raw(Address::from_raw(RCREG_ADDR)), 0);
        assert_eq!(mem.read_raw(Address::from_raw(PIR1_ADDR)) & PIR1_RCIF, 0);
        // TX side also drains -- the held byte and TSR
        // state are gone.
        assert!(
            eusart.tsr_busy_tcy.is_none(),
            "SPEN=0 must drain TSR busy state"
        );
        assert!(
            eusart.tsr_byte.is_none(),
            "SPEN=0 must drop in-flight TSR byte"
        );
        assert!(
            eusart.txreg_holding.is_none(),
            "SPEN=0 must drop held TXREG byte"
        );
        assert!(
            eusart.take_completed_tx_byte().is_none(),
            "SPEN=0 must drain completed-TX queue"
        );
        // TRMT re-asserts (TSR idle) so firmware that
        // polls TXSTA.TRMT after the SPEN-shutdown sees
        // a non-stale value.  Codex review of 6335c3a
        // MEDIUM.
        assert_eq!(
            mem.read_raw(Address::from_raw(TXSTA_ADDR)) & TXSTA_TRMT,
            TXSTA_TRMT,
            "SPEN=0 must reassert TRMT (TSR idle)"
        );
    }

    /// `on_sfr_read` is a no-op for non-RCREG addresses
    /// (defensive: a future caller wiring it through the
    /// memory dispatch must not clobber unrelated SFR
    /// state).
    #[test]
    fn on_sfr_read_noop_for_non_rcreg() {
        let mut eusart = Eusart::new(Variant::Pic18F25K20);
        let mut mem = fresh_mem();
        // Pre-set every PIR1 bit so any spurious clear is
        // visible.
        mem.write_raw(Address::from_raw(PIR1_ADDR), 0xFF);
        // Read TXREG, RCSTA, TXSTA, SPBRG, BAUDCON, PIR1
        // itself: none should change PIR1.
        for addr in [
            TXREG_ADDR,
            RCSTA_ADDR,
            TXSTA_ADDR,
            SPBRG_ADDR,
            BAUDCON_ADDR,
            PIR1_ADDR,
        ] {
            eusart.on_sfr_read(addr, &mut mem);
            assert_eq!(
                mem.read_raw(Address::from_raw(PIR1_ADDR)),
                0xFF,
                "on_sfr_read({:#X}) must not touch PIR1",
                addr
            );
        }
    }

    /// reset_state drains the completed-TX FIFO so a
    /// MCLR-then-bootstrap sequence doesn't deliver
    /// stale bytes to the peer.
    #[test]
    fn reset_state_drains_completed_tx_fifo() {
        let mut eusart = Eusart::new(Variant::Pic18F25K20);
        eusart.completed_tx_bytes.push_back(0xDE);
        eusart.completed_tx_bytes.push_back(0xAD);
        eusart.reset_state();
        assert!(eusart.take_completed_tx_byte().is_none());
    }

    /// `reset_state` clears any in-flight TX so a SLEEP-then-
    /// reset sequence doesn't carry a phantom frame across the
    /// boundary.
    #[test]
    fn reset_state_clears_in_flight_frame() {
        let mut eusart = Eusart::new(Variant::Pic18F25K20);
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(SPBRG_ADDR), 5);
        mem.write_raw(Address::from_raw(BAUDCON_ADDR), 0x40);
        enable_async_tx(&mut mem);
        eusart.on_sfr_write(TXREG_ADDR, 0x55, &mut mem);
        assert!(eusart.tsr_busy_tcy.is_some());

        eusart.reset_state();
        assert!(eusart.tsr_busy_tcy.is_none());
        assert!(eusart.txreg_holding.is_none());
    }
}
