//! Peripheral models for the PIC18F25K20 (CONTROL) and
//! PIC18F2455 (MAIN) cores.  Lives behind [`crate::core::Core`]
//! and is mutated by the executor through two hooks:
//!
//! * [`Peripherals::on_sfr_write`] — invoked from
//!   `exec::write_addr_masked` after a SW-driven SFR write
//!   lands in the backing memory.  Lets a peripheral observe
//!   the new value and, if it owns a status bit, update
//!   memory in place to reflect the new internal state (e.g.
//!   TXSTA.TRMT clears on TXREG write).
//! * [`Peripherals::tick_tcy`] — invoked from
//!   `Core::advance_cycles` after each instruction's Tcy
//!   count is added to the cycle counter.  Lets time-driven
//!   peripherals (baud generator, timers, ADC sample/conv,
//!   EEPROM post-write completion) progress in lock-step
//!   with the executor.
//!
//! Each peripheral keeps its own state struct plus the
//! glue inside this module.  The intent is that future Phase 3
//! / Phase 4 work can swap the polled `tick_tcy(n)` model out
//! for a global event queue without rewriting the per-peripheral
//! state machines (each peripheral exposes both a "tick by N
//! Tcy" entry point AND, eventually, "schedule next-edge
//! deadline" hooks).

pub mod eusart;
pub mod mssp;

use crate::memory::{Memory, Variant};

/// Bag-of-peripherals owned by [`crate::core::Core`].  Each
/// field is a peripheral's state machine.  Peripherals that
/// only exist on one variant (USB-SIE on 2455, EEADRH on
/// PIC18F26K20) carry their own variant-gated logic; the
/// container is variant-agnostic.
#[derive(Clone, Debug)]
pub struct Peripherals {
    pub eusart: eusart::Eusart,
    pub mssp: mssp::Mssp,
}

impl Peripherals {
    /// Build a fresh peripheral bag for `variant`.  All state
    /// is at POR; the executor's [`crate::reset::apply_reset`]
    /// call still owns the SFR-side POR table, which is read
    /// back by the peripherals when they tick the first time.
    pub fn new(variant: Variant) -> Self {
        Peripherals {
            eusart: eusart::Eusart::new(variant),
            mssp: mssp::Mssp::new(variant),
        }
    }

    /// Forward an SFR write to whichever peripheral owns
    /// behaviour for `addr`.  Most addresses are no-ops at the
    /// peripheral level — the memory write has already landed
    /// via `apply_sfr_sw_write`, and the peripheral only needs
    /// to react if the write triggers a side effect (DMA-style
    /// register, FIFO push, baud-generator reload, etc.).
    pub fn on_sfr_write(&mut self, addr: u16, value: u8, mem: &mut Memory) {
        self.eusart.on_sfr_write(addr, value, mem);
        self.mssp.on_sfr_write(addr, value, mem);
    }

    /// Advance every peripheral's internal time by `n` Tcy.
    /// Called from `Core::advance_cycles`.  `mem` is passed so
    /// peripherals can update their own status SFRs (TXSTA.TRMT,
    /// PIR1.TXIF, etc.) without needing a callback layer.
    pub fn tick_tcy(&mut self, n: u32, mem: &mut Memory) {
        self.eusart.tick_tcy(n, mem);
        self.mssp.tick_tcy(n, mem);
    }

    /// Throw away each peripheral's internal state machine.
    /// Called from `apply_reset` for every reset source so an
    /// in-flight TX frame / EEPROM write / ADC conversion
    /// doesn't survive a POR/BOR/MCLR/WDT/RESET into the next
    /// boot.  SFR-side defaults are restored separately by
    /// `apply_reset`'s POR table; this method only resets the
    /// non-SFR state hidden inside each peripheral struct.
    pub fn reset_state(&mut self) {
        self.eusart.reset_state();
        self.mssp.reset_state();
    }
}
