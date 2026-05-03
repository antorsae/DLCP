//! IRQ controller — Phase-2 SFR-semantic stub.
//!
//! ## Scope
//!
//! Phase-2 wires the *query* surface a future IRQ-aware
//! executor (Phase 3) will call at instruction boundaries:
//!
//!   * [`is_irq_pending_high`] / [`is_irq_pending_low`] /
//!     [`is_irq_pending`] inspect SFR memory and return
//!     whether an unmasked enabled flag is set under the
//!     current GIE/GIEH/GIEL/IPEN gate.
//!
//! It does NOT yet vector the executor to 0x0008 / 0x0018
//! on a pending IRQ -- that requires interleaving IRQ
//! delivery with the instruction fetch/decode loop, which
//! is the Phase-3 multi-core scheduler's job.  V1.71
//! cycle-10 boot never fires an IRQ so the deferral is
//! safe.
//!
//! ## SFR addresses (DS40001303H Tbl 5-1)
//!
//! | Addr  | Reg     | Role                                |
//! |-------|---------|-------------------------------------|
//! | 0xFF2 | INTCON  | GIE/GIEH, PEIE/GIEL, TMR0IE, INT0IE, RBIE, TMR0IF, INT0IF, RBIF |
//! | 0xFF1 | INTCON2 | RBPU/INTEDG0/INTEDG1/INTEDG2/TMR0IP/RBIP |
//! | 0xFF0 | INTCON3 | INT2IP/INT1IP/INT2IE/INT1IE/INT2IF/INT1IF |
//! | 0xFD0 | RCON    | IPEN/SBOREN/RI/TO/PD/POR/BOR        |
//! | 0xFA2 | IPR2    | OSCFIP/C1IP/C2IP/EEIP/BCLIP/HLVDIP/TMR3IP/CCP2IP |
//! | 0xFA1 | PIR2    | OSCFIF/C1IF/C2IF/EEIF/BCLIF/HLVDIF/TMR3IF/CCP2IF |
//! | 0xFA0 | PIE2    | OSCFIE/C1IE/C2IE/EEIE/BCLIE/HLVDIE/TMR3IE/CCP2IE |
//! | 0xF9F | IPR1    | PSPIP/ADIP/RCIP/TXIP/SSPIP/CCP1IP/TMR2IP/TMR1IP |
//! | 0xF9E | PIR1    | PSPIF/ADIF/RCIF/TXIF/SSPIF/CCP1IF/TMR2IF/TMR1IF |
//! | 0xF9D | PIE1    | PSPIE/ADIE/RCIE/TXIE/SSPIE/CCP1IE/TMR2IE/TMR1IE |

use crate::core::{Core, IrqContext};
use crate::memory::{Address, Memory, Variant};
use crate::stack::Stack;

pub const INTCON_ADDR: u16 = 0xFF2;
pub const INTCON2_ADDR: u16 = 0xFF1;
pub const INTCON3_ADDR: u16 = 0xFF0;
pub const RCON_ADDR: u16 = 0xFD0;
pub const IPR2_ADDR: u16 = 0xFA2;
pub const PIR2_ADDR: u16 = 0xFA1;
pub const PIE2_ADDR: u16 = 0xFA0;
pub const IPR1_ADDR: u16 = 0xF9F;
pub const PIR1_ADDR: u16 = 0xF9E;
pub const PIE1_ADDR: u16 = 0xF9D;

const INTCON_GIE_GIEH: u8 = 1 << 7;
const INTCON_PEIE_GIEL: u8 = 1 << 6;
const RCON_IPEN: u8 = 1 << 7;

#[derive(Clone, Debug, Default)]
pub struct Irq;

impl Irq {
    pub fn new(_variant: Variant) -> Self {
        Irq
    }
    pub fn reset_state(&mut self) {}
    pub fn on_sfr_write(&mut self, _addr: u16, _value: u8, _mem: &mut Memory) {}
    pub fn tick_tcy(&mut self, _n: u32, _mem: &mut Memory) {}
}

/// Return true iff a high-priority IRQ is currently pending
/// and unmasked.  In IPEN=0 (compat) mode every IRQ is
/// "high"; in IPEN=1 only IRQs with IPRx bit set count as
/// high.  GIE/GIEH (INTCON bit 7) is the master enable in
/// both modes.
pub fn is_irq_pending_high(mem: &Memory) -> bool {
    let intcon = mem.read_raw(Address::from_raw(INTCON_ADDR));
    if intcon & INTCON_GIE_GIEH == 0 {
        return false;
    }
    let rcon = mem.read_raw(Address::from_raw(RCON_ADDR));
    let ipen = rcon & RCON_IPEN != 0;
    let core_intcon_pending = intcon_pending(mem);
    if !ipen {
        // IPEN=0 (compatibility mode): every pending+enabled
        // flag counts as "high".  Peripheral IRQs require
        // PEIE/GIEL (INTCON bit 6) -- per DS section 9.1, in
        // compat mode INTCON<6> is the master enable for
        // peripheral sources; INTCON-residing flags (TMR0,
        // INT0, RB, INTCON3 INT1/INT2) only need GIE/GIEH.
        let peie = intcon & INTCON_PEIE_GIEL != 0;
        let peripheral_active = peie && peripheral_pending(mem, false);
        return core_intcon_pending || peripheral_active;
    }
    // IPEN=1: only flags with their priority bit = 1 count
    // as high.
    intcon_pending_priority(mem, true) || peripheral_pending(mem, true)
}

/// Return true iff a low-priority IRQ is currently pending
/// and unmasked.  Only meaningful when IPEN=1 AND
/// PEIE/GIEL=1.  In IPEN=0 mode, all IRQs are "high" -- this
/// returns false.
pub fn is_irq_pending_low(mem: &Memory) -> bool {
    let intcon = mem.read_raw(Address::from_raw(INTCON_ADDR));
    let rcon = mem.read_raw(Address::from_raw(RCON_ADDR));
    let ipen = rcon & RCON_IPEN != 0;
    if !ipen {
        return false;
    }
    if intcon & INTCON_GIE_GIEH == 0 || intcon & INTCON_PEIE_GIEL == 0 {
        return false;
    }
    intcon_pending_priority(mem, false) || peripheral_pending(mem, false)
}

/// Convenience: any IRQ pending (high OR low).
pub fn is_irq_pending(mem: &Memory) -> bool {
    is_irq_pending_high(mem) || is_irq_pending_low(mem)
}

/// PIC18 high-priority interrupt vector address (DS39632E
/// §9.3, DS40001303H §9.3).  Same on both K20 and 2455.
pub const IRQ_VECTOR_HIGH: u32 = 0x0008;
/// Low-priority interrupt vector address.  Only used when
/// RCON.IPEN=1.
pub const IRQ_VECTOR_LOW: u32 = 0x0018;

/// Try to dispatch a pending interrupt at the current
/// instruction boundary.  Returns the Tcy cost of the
/// vector entry if an interrupt was taken, or `None` if
/// no interrupt is pending or the gates are closed.
///
/// On entry: pushes the caller's PC onto the hardware stack
/// (so RETFIE can return to it), clears the appropriate GIE
/// bit (GIE in IPEN=0; GIEH for high/GIEL for low in
/// IPEN=1), and sets PC to the matching vector
/// (`IRQ_VECTOR_HIGH` or `IRQ_VECTOR_LOW`).
///
/// **Phase-3.5 minimum-viable scope** (task #28):
///
/// * IPEN=0 (compatibility) and IPEN=1 (priority) modes both
///   recognised; vector selection follows priority in
///   IPEN=1.
/// * Fast-stack push of WREG/STATUS/BSR (DS §5.5.3) IS now
///   modelled in both IPEN modes (task #15).  Every
///   successful vector entry calls `core.save_fast_regs()`
///   so a matching `RETFIE FAST` restores the snapshot.
/// * Stack-full reset is honoured during IRQ vectoring
///   (task #16): if the return-PC push is the FILLING push
///   (depth 30->31, STKFUL latches) and `STVREN=1`, the
///   dispatch fires `apply_reset(StackFull)` and returns
///   without clearing GIE or setting the vector PC.
/// * Cost is reported as 2 Tcy (fetch+vector).  Real silicon
///   takes 1-2 Tcy depending on the in-flight instruction;
///   close enough for Phase-3.5 cycle accounting.
pub fn try_dispatch_irq(core: &mut Core, stack: &mut Stack) -> Option<u8> {
    // Snapshot the gate state up-front to choose the vector.
    // Read directly off the SFR window -- callers (the
    // executor) hold a `&mut Core` so we have the access we
    // need for both reads and the post-decision writes.
    let mem_ref: &Memory = &core.memory;
    let intcon = mem_ref.read_raw(Address::from_raw(INTCON_ADDR));
    let rcon = mem_ref.read_raw(Address::from_raw(RCON_ADDR));
    let ipen = (rcon & RCON_IPEN) != 0;

    // GIE/GIEH gate -- IPEN=0 master, IPEN=1 high-priority master.
    let gieh = (intcon & INTCON_GIE_GIEH) != 0;
    if !gieh {
        return None;
    }

    // Per DS39632E §5.5.3 ("It is loaded with the current
    // value of the corresponding register when the
    // processor vectors for an interrupt.  All interrupt
    // sources will push values into the stack registers.")
    // -- the fast shadow is pushed on EVERY interrupt
    // dispatch, regardless of IPEN.  In IPEN=0
    // (compatibility) mode, "all interrupts may use the
    // Fast Register Stack for returns from interrupt"
    // (§5.5.3 again) -- so the push is unconditional.

    if !ipen {
        // IPEN=0 (compatibility): single vector, single gate.
        if !is_irq_pending_high(mem_ref) {
            return None;
        }
        let return_pc = core.pc();
        let pushed = stack.push(return_pc);
        stack.mirror_to_sfrs(&mut core.memory);
        if pushed
            && stack.depth() as usize == crate::stack::STACK_DEPTH
            && core.config.stvren()
        {
            // Stack-full reset during IRQ dispatch.  Per
            // DS39632E §5.1.2.4 the push that takes the
            // stack to depth=31 ("becomes full") triggers
            // the reset; STKFUL latches as a side effect.
            // Do NOT save fast regs, clear GIE, or set the
            // vector PC -- the reset preempts vectoring.
            // Stack-full reset uses the MCLR-style SFR
            // reset path (Tbl 4-4 column 6), which clears
            // INTCON.GIE so the very next step cannot
            // immediately re-vector.  Codex review of
            // 2fa7d0a MEDIUM 3 + 41d6195 MEDIUM (trigger
            // is the FILLING push) + 5a315b3 MEDIUM
            // (trigger keyed to depth-becomes-full, not
            // STKFUL latch transition).
            crate::reset::apply_reset(
                core,
                stack,
                crate::reset::ResetSource::StackFull,
            );
            stack.mirror_to_sfrs(&mut core.memory);
            return Some(2);
        }
        core.save_fast_regs();
        core.push_irq_context(IrqContext::Compatibility);
        // Clear GIE.
        let mem = &mut core.memory;
        let new_intcon = intcon & !INTCON_GIE_GIEH;
        mem.write_raw(Address::from_raw(INTCON_ADDR), new_intcon);
        core.set_pc(IRQ_VECTOR_HIGH);
        return Some(2);
    }

    // IPEN=1: high-priority IRQs go to 0x0008 and clear GIEH;
    // low-priority IRQs go to 0x0018 and clear GIEL.  Check
    // high before low so a same-cycle high+low pending pair
    // takes the high path first (per DS §9.3 priority order).
    //
    // Caveat in IPEN=1: per DS §5.5.3, "If a high-priority
    // interrupt occurs while servicing a low-priority
    // interrupt, the stack register values stored by the
    // low-priority interrupt will be overwritten."  Our
    // 1-deep shadow models that exact corruption mode --
    // firmware that runs both priorities is expected to
    // save/restore in software during the low-priority ISR.
    if is_irq_pending_high(mem_ref) {
        let return_pc = core.pc();
        let pushed = stack.push(return_pc);
        stack.mirror_to_sfrs(&mut core.memory);
        if pushed
            && stack.depth() as usize == crate::stack::STACK_DEPTH
            && core.config.stvren()
        {
            crate::reset::apply_reset(
                core,
                stack,
                crate::reset::ResetSource::StackFull,
            );
            stack.mirror_to_sfrs(&mut core.memory);
            return Some(2);
        }
        core.save_fast_regs();
        core.push_irq_context(IrqContext::High);
        let mem = &mut core.memory;
        let new_intcon = intcon & !INTCON_GIE_GIEH;
        mem.write_raw(Address::from_raw(INTCON_ADDR), new_intcon);
        core.set_pc(IRQ_VECTOR_HIGH);
        return Some(2);
    }
    if is_irq_pending_low(mem_ref) {
        let return_pc = core.pc();
        let pushed = stack.push(return_pc);
        stack.mirror_to_sfrs(&mut core.memory);
        if pushed
            && stack.depth() as usize == crate::stack::STACK_DEPTH
            && core.config.stvren()
        {
            crate::reset::apply_reset(
                core,
                stack,
                crate::reset::ResetSource::StackFull,
            );
            stack.mirror_to_sfrs(&mut core.memory);
            return Some(2);
        }
        core.save_fast_regs();
        core.push_irq_context(IrqContext::Low);
        let mem = &mut core.memory;
        let new_intcon = intcon & !INTCON_PEIE_GIEL;
        mem.write_raw(Address::from_raw(INTCON_ADDR), new_intcon);
        core.set_pc(IRQ_VECTOR_LOW);
        return Some(2);
    }
    None
}

/// Restore the appropriate GIE bit on RETFIE.
///
/// Per DS39632E §9.3: RETFIE always sets GIEH=1 (the
/// high-priority gate).  In IPEN=1 mode, returning from a
/// LOW-priority ISR also re-enables GIEL.  Without
/// hardware-tracked "which ISR are we in?" state, the
/// safe approximation is: always set both GIEH and
/// (if IPEN=1) GIEL.  In IPEN=0 mode GIEL/PEIE is
/// untouched -- it serves a different role
/// (peripheral-master-enable).
pub fn restore_gie_on_retfie(mem: &mut Memory, context: Option<IrqContext>) {
    let rcon = mem.read_raw(Address::from_raw(RCON_ADDR));
    let ipen = (rcon & RCON_IPEN) != 0;
    let intcon = mem.read_raw(Address::from_raw(INTCON_ADDR));
    let new_intcon = if !ipen {
        intcon | INTCON_GIE_GIEH
    } else {
        match context {
            Some(IrqContext::Low) => intcon | INTCON_PEIE_GIEL,
            Some(IrqContext::High) => intcon | INTCON_GIE_GIEH,
            Some(IrqContext::Compatibility) | None => intcon | INTCON_GIE_GIEH | INTCON_PEIE_GIEL,
        }
    };
    mem.write_raw(Address::from_raw(INTCON_ADDR), new_intcon);
}

/// True if any INTCON-residing flag is enabled+set
/// (regardless of priority).  Used for IPEN=0 mode.
fn intcon_pending(mem: &Memory) -> bool {
    let intcon = mem.read_raw(Address::from_raw(INTCON_ADDR));
    let intcon3 = mem.read_raw(Address::from_raw(INTCON3_ADDR));
    // INTCON: TMR0IE (5) & TMR0IF (2); INT0IE (4) & INT0IF (1);
    //         RBIE (3) & RBIF (0).
    let intcon_flags = (intcon & 0x20 != 0 && intcon & 0x04 != 0)
        || (intcon & 0x10 != 0 && intcon & 0x02 != 0)
        || (intcon & 0x08 != 0 && intcon & 0x01 != 0);
    // INTCON3: INT1IE (3) & INT1IF (0); INT2IE (4) & INT2IF (1).
    let intcon3_flags = (intcon3 & 0x08 != 0 && intcon3 & 0x01 != 0)
        || (intcon3 & 0x10 != 0 && intcon3 & 0x02 != 0);
    intcon_flags || intcon3_flags
}

/// Same as `intcon_pending` but priority-filtered: only
/// returns true if any pending+enabled flag's priority bit
/// matches `want_high`.  INT0 is ALWAYS high-priority on
/// PIC18 (no priority bit; hardware-fixed).  TMR0 priority
/// = INTCON2.TMR0IP (bit 2).  RB priority = INTCON2.RBIP
/// (bit 0).  INT1 priority = INTCON3.INT1IP (bit 6).  INT2
/// priority = INTCON3.INT2IP (bit 7).
fn intcon_pending_priority(mem: &Memory, want_high: bool) -> bool {
    let intcon = mem.read_raw(Address::from_raw(INTCON_ADDR));
    let intcon2 = mem.read_raw(Address::from_raw(INTCON2_ADDR));
    let intcon3 = mem.read_raw(Address::from_raw(INTCON3_ADDR));
    // TMR0: en=INTCON.5 flag=INTCON.2 prio=INTCON2.2.
    let tmr0_pending = intcon & 0x20 != 0 && intcon & 0x04 != 0;
    let tmr0_high = intcon2 & 0x04 != 0;
    if tmr0_pending && tmr0_high == want_high {
        return true;
    }
    // INT0: en=INTCON.4 flag=INTCON.1 prio=ALWAYS high.
    let int0_pending = intcon & 0x10 != 0 && intcon & 0x02 != 0;
    if int0_pending && want_high {
        return true;
    }
    // RB: en=INTCON.3 flag=INTCON.0 prio=INTCON2.0.
    let rb_pending = intcon & 0x08 != 0 && intcon & 0x01 != 0;
    let rb_high = intcon2 & 0x01 != 0;
    if rb_pending && rb_high == want_high {
        return true;
    }
    // INT1: en=INTCON3.3 flag=INTCON3.0 prio=INTCON3.6.
    let int1_pending = intcon3 & 0x08 != 0 && intcon3 & 0x01 != 0;
    let int1_high = intcon3 & 0x40 != 0;
    if int1_pending && int1_high == want_high {
        return true;
    }
    // INT2: en=INTCON3.4 flag=INTCON3.1 prio=INTCON3.7.
    let int2_pending = intcon3 & 0x10 != 0 && intcon3 & 0x02 != 0;
    let int2_high = intcon3 & 0x80 != 0;
    if int2_pending && int2_high == want_high {
        return true;
    }
    false
}

/// True if any peripheral IRQ (PIRx & PIEx) is enabled and
/// set.  In IPEN=0 mode, called with `want_high=false` to
/// mean "any peripheral".  In IPEN=1 mode, filtered by IPRx.
fn peripheral_pending(mem: &Memory, ipen_high_filter: bool) -> bool {
    let pir1 = mem.read_raw(Address::from_raw(PIR1_ADDR));
    let pie1 = mem.read_raw(Address::from_raw(PIE1_ADDR));
    let ipr1 = mem.read_raw(Address::from_raw(IPR1_ADDR));
    let pir2 = mem.read_raw(Address::from_raw(PIR2_ADDR));
    let pie2 = mem.read_raw(Address::from_raw(PIE2_ADDR));
    let ipr2 = mem.read_raw(Address::from_raw(IPR2_ADDR));

    let active1 = pir1 & pie1;
    let active2 = pir2 & pie2;
    let rcon = mem.read_raw(Address::from_raw(RCON_ADDR));
    let ipen = rcon & RCON_IPEN != 0;
    if !ipen {
        return active1 != 0 || active2 != 0;
    }
    // IPEN=1: filter by per-bit IPRx.
    let high1 = active1 & ipr1;
    let low1 = active1 & !ipr1;
    let high2 = active2 & ipr2;
    let low2 = active2 & !ipr2;
    if ipen_high_filter {
        high1 != 0 || high2 != 0
    } else {
        low1 != 0 || low2 != 0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fresh_mem() -> Memory {
        // Use 25K20 variant; reset.rs's K20_POR table sets
        // IPR1/IPR2/INTCON2/INTCON3 to non-zero defaults
        // which would trip these tests.  Fresh Memory has
        // all-zero contents.
        Memory::new(Variant::Pic18F25K20)
    }

    #[test]
    fn no_pending_after_clean_init() {
        let mem = fresh_mem();
        assert!(!is_irq_pending(&mem));
    }

    #[test]
    fn ipen0_compat_mode_peripheral_irq_requires_peie_and_gie() {
        let mut mem = fresh_mem();
        // Enable + flag TMR1IF (PIE1.0 + PIR1.0).
        mem.write_raw(Address::from_raw(PIE1_ADDR), 0x01);
        mem.write_raw(Address::from_raw(PIR1_ADDR), 0x01);
        // GIE=1 only (PEIE=0): peripheral source must NOT
        // fire in compat mode.
        mem.write_raw(Address::from_raw(INTCON_ADDR), INTCON_GIE_GIEH);
        assert!(
            !is_irq_pending_high(&mem),
            "compat mode requires PEIE for peripheral sources"
        );
        // GIE=1 and PEIE=1: now it fires.
        mem.write_raw(
            Address::from_raw(INTCON_ADDR),
            INTCON_GIE_GIEH | INTCON_PEIE_GIEL,
        );
        assert!(is_irq_pending_high(&mem));
        assert!(!is_irq_pending_low(&mem));
    }

    #[test]
    fn ipen0_compat_mode_intcon_source_does_not_need_peie() {
        let mut mem = fresh_mem();
        // TMR0IE=INTCON.5, TMR0IF=INTCON.2 are in INTCON
        // itself, so PEIE is NOT required to deliver them
        // in compat mode.
        mem.write_raw(
            Address::from_raw(INTCON_ADDR),
            INTCON_GIE_GIEH | 0x20 | 0x04, // GIE | TMR0IE | TMR0IF
        );
        assert!(is_irq_pending_high(&mem));
    }

    #[test]
    fn ipen0_compat_mode_no_pending_when_gie_clear() {
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(PIE1_ADDR), 0x01);
        mem.write_raw(Address::from_raw(PIR1_ADDR), 0x01);
        // GIE=0.
        mem.write_raw(Address::from_raw(INTCON_ADDR), 0);
        assert!(!is_irq_pending(&mem));
    }

    #[test]
    fn ipen1_high_filter_via_ipr1() {
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(RCON_ADDR), RCON_IPEN);
        // GIE/GIEH=1 + PEIE/GIEL=1 (both required for low-prio
        // delivery in IPEN=1).
        mem.write_raw(
            Address::from_raw(INTCON_ADDR),
            INTCON_GIE_GIEH | INTCON_PEIE_GIEL,
        );
        // TMR1: PIE=1, PIR=1, IPR=1 (high).
        mem.write_raw(Address::from_raw(PIE1_ADDR), 0x01);
        mem.write_raw(Address::from_raw(PIR1_ADDR), 0x01);
        mem.write_raw(Address::from_raw(IPR1_ADDR), 0x01);
        assert!(is_irq_pending_high(&mem));
        assert!(!is_irq_pending_low(&mem));
    }

    #[test]
    fn ipen1_low_filter_via_ipr1() {
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(RCON_ADDR), RCON_IPEN);
        mem.write_raw(
            Address::from_raw(INTCON_ADDR),
            INTCON_GIE_GIEH | INTCON_PEIE_GIEL,
        );
        // TMR1: PIE=1, PIR=1, IPR=0 (low).
        mem.write_raw(Address::from_raw(PIE1_ADDR), 0x01);
        mem.write_raw(Address::from_raw(PIR1_ADDR), 0x01);
        mem.write_raw(Address::from_raw(IPR1_ADDR), 0x00);
        assert!(!is_irq_pending_high(&mem));
        assert!(is_irq_pending_low(&mem));
    }

    #[test]
    fn ipen1_low_blocked_by_giel_clear() {
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(RCON_ADDR), RCON_IPEN);
        // GIE=1 but PEIE/GIEL=0.
        mem.write_raw(Address::from_raw(INTCON_ADDR), INTCON_GIE_GIEH);
        mem.write_raw(Address::from_raw(PIE1_ADDR), 0x01);
        mem.write_raw(Address::from_raw(PIR1_ADDR), 0x01);
        mem.write_raw(Address::from_raw(IPR1_ADDR), 0x00);
        assert!(!is_irq_pending_low(&mem));
    }

    #[test]
    fn intcon_int0_always_high_priority() {
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(RCON_ADDR), RCON_IPEN);
        mem.write_raw(
            Address::from_raw(INTCON_ADDR),
            INTCON_GIE_GIEH | 0x10 | 0x02, // GIE | INT0IE | INT0IF
        );
        assert!(is_irq_pending_high(&mem));
    }

    // ---------- try_dispatch_irq + restore_gie_on_retfie ----------

    fn k20_core_at_pc(pc: u32) -> Core {
        let mut core = Core::new(Variant::Pic18F25K20);
        core.set_pc(pc);
        core
    }

    /// IPEN=0 + GIE set + INT0 pending -> dispatch to 0x0008,
    /// PC pushed, GIE cleared.
    #[test]
    fn try_dispatch_irq_ipen0_takes_high_vector() {
        let mut core = k20_core_at_pc(0x1234);
        let mut stack = Stack::new();
        // INT0IE | INT0IF | GIE = 0x90 + 0x02 = 0x92
        core.memory.write_raw(
            Address::from_raw(INTCON_ADDR),
            INTCON_GIE_GIEH | 0x10 | 0x02,
        );
        let cycles = try_dispatch_irq(&mut core, &mut stack);
        assert_eq!(cycles, Some(2));
        assert_eq!(core.pc(), IRQ_VECTOR_HIGH);
        assert_eq!(stack.top(), 0x1234);
        // GIE cleared (other bits preserved).
        let intcon = core.memory.read_raw(Address::from_raw(INTCON_ADDR));
        assert_eq!(intcon & INTCON_GIE_GIEH, 0);
        assert_eq!(intcon & 0x12, 0x12, "INT0IE / INT0IF preserved");
    }

    /// GIE clear -> no dispatch, no state changes.
    #[test]
    fn try_dispatch_irq_gie_clear_no_dispatch() {
        let mut core = k20_core_at_pc(0x1234);
        let mut stack = Stack::new();
        // INT0IE | INT0IF set but GIE clear.
        core.memory.write_raw(Address::from_raw(INTCON_ADDR), 0x12);
        let cycles = try_dispatch_irq(&mut core, &mut stack);
        assert!(cycles.is_none());
        assert_eq!(core.pc(), 0x1234);
        assert_eq!(stack.depth(), 0);
    }

    /// No pending IRQ -> no dispatch.
    #[test]
    fn try_dispatch_irq_no_pending_no_dispatch() {
        let mut core = k20_core_at_pc(0x1234);
        let mut stack = Stack::new();
        core.memory
            .write_raw(Address::from_raw(INTCON_ADDR), INTCON_GIE_GIEH);
        let cycles = try_dispatch_irq(&mut core, &mut stack);
        assert!(cycles.is_none());
        assert_eq!(core.pc(), 0x1234);
    }

    /// IPEN=1 + low-priority IRQ pending + GIEH+GIEL set ->
    /// dispatch to 0x0018, GIEL cleared, GIEH preserved.
    #[test]
    fn try_dispatch_irq_ipen1_takes_low_vector() {
        let mut core = k20_core_at_pc(0x4000);
        let mut stack = Stack::new();
        core.memory
            .write_raw(Address::from_raw(RCON_ADDR), RCON_IPEN);
        // GIE | PEIE both set; PEIE=1 means GIEL in IPEN=1.
        core.memory.write_raw(
            Address::from_raw(INTCON_ADDR),
            INTCON_GIE_GIEH | INTCON_PEIE_GIEL,
        );
        // Low-priority TMR1 IRQ pending.  PIE1 bit 0 = TMR1IE,
        // PIR1 bit 0 = TMR1IF, IPR1 bit 0 = TMR1IP (0 = low).
        core.memory.write_raw(Address::from_raw(PIE1_ADDR), 0x01);
        core.memory.write_raw(Address::from_raw(PIR1_ADDR), 0x01);
        core.memory.write_raw(Address::from_raw(IPR1_ADDR), 0x00);
        let cycles = try_dispatch_irq(&mut core, &mut stack);
        assert_eq!(cycles, Some(2));
        assert_eq!(core.pc(), IRQ_VECTOR_LOW);
        assert_eq!(stack.top(), 0x4000);
        // GIEL cleared, GIEH still set.
        let intcon = core.memory.read_raw(Address::from_raw(INTCON_ADDR));
        assert_eq!(intcon & INTCON_GIE_GIEH, INTCON_GIE_GIEH);
        assert_eq!(intcon & INTCON_PEIE_GIEL, 0);
    }

    /// IPEN=1 with both HIGH AND LOW pending simultaneously:
    /// high wins (priority order, DS §9.3).  Pin both
    /// sources active to validate the tie-break rather than
    /// just "high pending alone goes high".
    #[test]
    fn try_dispatch_irq_ipen1_high_wins_over_low() {
        let mut core = k20_core_at_pc(0x4000);
        let mut stack = Stack::new();
        core.memory
            .write_raw(Address::from_raw(RCON_ADDR), RCON_IPEN);
        core.memory.write_raw(
            Address::from_raw(INTCON_ADDR),
            INTCON_GIE_GIEH | INTCON_PEIE_GIEL,
        );
        // Two PIR1 sources pending+enabled: bit 0 = TMR1IF
        // (high-priority via IPR1.bit0 = 1) AND bit 1 = TMR2IF
        // (low-priority via IPR1.bit1 = 0).
        core.memory.write_raw(Address::from_raw(PIE1_ADDR), 0x03);
        core.memory.write_raw(Address::from_raw(PIR1_ADDR), 0x03);
        core.memory.write_raw(Address::from_raw(IPR1_ADDR), 0x01);
        // Sanity: both pending paths see traffic.
        assert!(is_irq_pending_high(&core.memory));
        assert!(is_irq_pending_low(&core.memory));
        let cycles = try_dispatch_irq(&mut core, &mut stack);
        assert_eq!(cycles, Some(2));
        assert_eq!(core.pc(), IRQ_VECTOR_HIGH);
        // GIEH cleared, GIEL preserved -- low IRQ stays
        // pending until a future RETFIE re-enables GIEH and
        // the low source wins on the next dispatch.
        let intcon = core.memory.read_raw(Address::from_raw(INTCON_ADDR));
        assert_eq!(intcon & INTCON_GIE_GIEH, 0);
        assert_eq!(intcon & INTCON_PEIE_GIEL, INTCON_PEIE_GIEL);
    }

    /// End-to-end round-trip through `exec::step`: enter ISR
    /// vector, RETFIE back to the original PC, GIE
    /// re-enabled.  Exercises the IRQ-dispatch + RETFIE
    /// integration through the executor.
    #[test]
    fn irq_round_trip_dispatches_runs_isr_and_returns() {
        use crate::exec::step;
        // Flash layout:
        //   0x0000: NOP (where the "main" was about to run)
        //   0x0008: RETFIE 0 (high-priority ISR vector --
        //                     immediately return)
        // RETFIE 0 encoding: 0x0010 = bytes [0x10, 0x00].
        let mut core = Core::new(Variant::Pic18F25K20);
        // Set "main code" PC.  We pretend main was at 0x0042
        // when the IRQ fires.
        core.set_pc(0x0042);
        // Bake a RETFIE at the high-priority vector.
        let flash = core.flash_mut();
        flash[0x0008] = 0x10;
        flash[0x0009] = 0x00;
        // Bake a NOP at 0x0042 so a follow-up step from the
        // restored PC finds something to execute.
        flash[0x0042] = 0x00;
        flash[0x0043] = 0x00;
        // Pre-IRQ state: IPEN=0, GIE+INT0IE+INT0IF set.
        core.memory.write_raw(
            Address::from_raw(INTCON_ADDR),
            INTCON_GIE_GIEH | 0x10 | 0x02,
        );
        let mut stack = Stack::new();

        // Step 1: IRQ should dispatch (no instruction
        // fetched), 2 Tcy cost, PC = 0x0008.
        let c1 = step(&mut core, &mut stack).unwrap();
        assert_eq!(c1, 2);
        assert_eq!(core.pc(), IRQ_VECTOR_HIGH);
        // Stack holds the pre-IRQ PC.
        assert_eq!(stack.top(), 0x0042);
        // GIE cleared.
        let intcon = core.memory.read_raw(Address::from_raw(INTCON_ADDR));
        assert_eq!(intcon & INTCON_GIE_GIEH, 0);

        // Step 2: ISR runs RETFIE -- pops PC, sets GIE.  But
        // INT0IF is still set, so the very next step will
        // re-dispatch unless we clear the flag.  Real ISRs
        // clear IF before RETFIE; we do the same here via a
        // single memory write that clears INT0IF (bit 1)
        // while preserving INT0IE (bit 4) and the GIE bit
        // currently held by `intcon` (which is 0 from the
        // step-1 dispatch -- correct: GIE is supposed to
        // stay clear inside an ISR until RETFIE re-enables
        // it).
        let int_flag_cleared = intcon & !0x02; // clear INT0IF only
        core.memory.write_raw(Address::from_raw(INTCON_ADDR), int_flag_cleared);
        let c2 = step(&mut core, &mut stack).unwrap();
        assert_eq!(c2, 2, "RETFIE billed at 2 Tcy");
        assert_eq!(core.pc(), 0x0042, "RETFIE restored pre-IRQ PC");
        // GIE re-enabled by RETFIE.
        let intcon2 = core.memory.read_raw(Address::from_raw(INTCON_ADDR));
        assert_eq!(
            intcon2 & INTCON_GIE_GIEH,
            INTCON_GIE_GIEH,
            "RETFIE must re-enable GIE"
        );

        // Step 3: would normally fetch NOP at 0x0042, but
        // since INT0IF is now clear no IRQ re-dispatches.
        let c3 = step(&mut core, &mut stack).unwrap();
        assert_eq!(c3, 1, "NOP at 0x0042 runs in 1 Tcy");
        assert_eq!(core.pc(), 0x0044);
    }

    /// Task #15: `Core::save_fast_regs` / `restore_fast_regs`
    /// snapshot and restore W/STATUS/BSR through a 1-deep
    /// shadow.  Required for V3.1's `CALL FAST` +
    /// `RETFIE 1` ISR idiom.
    #[test]
    fn fast_regs_save_and_restore_round_trip() {
        let mut core = Core::new(Variant::Pic18F25K20);
        // Stage initial W/STATUS/BSR via direct memory writes
        // so the test doesn't depend on the executor.
        core.memory
            .write_raw(Address::from_raw(0xFE8), 0xAB); // WREG
        core.memory
            .write_raw(Address::from_raw(0xFD8), 0x1F); // STATUS (5 LSBs)
        core.memory
            .write_raw(Address::from_raw(0xFE0), 0x05); // BSR
        core.save_fast_regs();
        // Clobber.
        core.memory
            .write_raw(Address::from_raw(0xFE8), 0x00);
        core.memory
            .write_raw(Address::from_raw(0xFD8), 0x00);
        core.memory
            .write_raw(Address::from_raw(0xFE0), 0x00);
        core.restore_fast_regs();
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xFE8)),
            0xAB,
            "WREG must restore"
        );
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xFD8)),
            0x1F,
            "STATUS must restore"
        );
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xFE0)),
            0x05,
            "BSR must restore (low nibble)"
        );
    }

    /// IRQ entry pushes the fast shadow regardless of IPEN
    /// per DS39632E §5.5.3 ("All interrupt sources will
    /// push values into the stack registers"; "If
    /// interrupt priority is not used, all interrupts may
    /// use the Fast Register Stack for returns from
    /// interrupt").  Verify both modes push.
    #[test]
    fn irq_dispatch_pushes_fast_shadow_in_both_ipen_modes() {
        // IPEN=0 path: IRQ entry MUST push current W/STATUS/BSR
        // onto the shadow.
        let mut core = Core::new(Variant::Pic18F25K20);
        core.set_pc(0x0042);
        core.memory
            .write_raw(Address::from_raw(INTCON_ADDR), INTCON_GIE_GIEH | 0x10 | 0x02);
        core.memory.write_raw(Address::from_raw(0xFE8), 0x66); // WREG
        core.memory.write_raw(Address::from_raw(0xFD8), 0x07); // STATUS
        core.memory.write_raw(Address::from_raw(0xFE0), 0x02); // BSR
        let mut stack = Stack::new();
        try_dispatch_irq(&mut core, &mut stack).unwrap();
        assert_eq!(core.fast_shadow.wreg, 0x66, "IPEN=0 IRQ pushes WREG");
        assert_eq!(core.fast_shadow.status, 0x07);
        assert_eq!(core.fast_shadow.bsr, 0x02);

        // IPEN=1 path: same contract.
        let mut core = Core::new(Variant::Pic18F25K20);
        core.set_pc(0x0042);
        core.memory
            .write_raw(Address::from_raw(RCON_ADDR), RCON_IPEN);
        core.memory.write_raw(
            Address::from_raw(INTCON_ADDR),
            INTCON_GIE_GIEH | 0x10 | 0x02,
        );
        core.memory.write_raw(Address::from_raw(0xFE8), 0xAA);
        core.memory.write_raw(Address::from_raw(0xFD8), 0x0F);
        core.memory.write_raw(Address::from_raw(0xFE0), 0x03);
        core.fast_shadow = crate::core::FastRegs::default();
        let mut stack = Stack::new();
        try_dispatch_irq(&mut core, &mut stack).unwrap();
        assert_eq!(core.fast_shadow.wreg, 0xAA, "IPEN=1 IRQ pushes WREG");
        assert_eq!(core.fast_shadow.status, 0x0F);
        assert_eq!(core.fast_shadow.bsr, 0x03);
    }

    /// IRQ entry mirrors the new TOS into 0xFFC..0xFFF SFRs
    /// so firmware reads match the canonical Stack state.
    #[test]
    fn irq_dispatch_mirrors_stack_into_tos_sfrs() {
        let mut core = Core::new(Variant::Pic18F25K20);
        core.set_pc(0x1234);
        core.memory
            .write_raw(Address::from_raw(INTCON_ADDR), INTCON_GIE_GIEH | 0x10 | 0x02);
        let mut stack = Stack::new();
        try_dispatch_irq(&mut core, &mut stack).unwrap();
        // Pushed PC = 0x001234.  SFR mirror must reflect it.
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFFC)), 1, "STKPTR depth=1");
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFFD)), 0x34, "TOSL");
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFFE)), 0x12, "TOSH");
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFFF)), 0x00, "TOSU");
    }

    /// After RETFIE, if a (different) IRQ flag is still
    /// pending, the very next step re-dispatches.  Locks in
    /// the back-to-back ISR pattern: ISR clears one flag,
    /// RETFIE re-enables GIE, another flag immediately
    /// triggers a new vector entry.
    #[test]
    fn irq_redispatches_immediately_after_retfie_if_still_pending() {
        use crate::exec::step;
        let mut core = Core::new(Variant::Pic18F25K20);
        // First-IRQ pre-PC = 0x0042.
        core.set_pc(0x0042);
        let flash = core.flash_mut();
        flash[0x0008] = 0x10; // RETFIE
        flash[0x0009] = 0x00;
        // INT0 pending+enabled, GIE set.
        core.memory.write_raw(
            Address::from_raw(INTCON_ADDR),
            INTCON_GIE_GIEH | 0x10 | 0x02,
        );
        let mut stack = Stack::new();

        // First IRQ: dispatch.  Stack push #1 at depth 1.
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.pc(), IRQ_VECTOR_HIGH);
        assert_eq!(stack.depth(), 1);
        // RETFIE: pops PC, re-enables GIE.  We do NOT clear
        // INT0IF.  Stack now empty (depth 0).
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.pc(), 0x0042);
        assert_eq!(stack.depth(), 0, "RETFIE must pop the stack");
        // Third step: IRQ still pending + GIE re-enabled ->
        // re-dispatch immediately.  Stack push #2 at depth 1.
        step(&mut core, &mut stack).unwrap();
        assert_eq!(
            core.pc(),
            IRQ_VECTOR_HIGH,
            "IRQ must re-dispatch immediately after RETFIE if flag still pending"
        );
        assert_eq!(
            stack.depth(),
            1,
            "redispatch must push a NEW stack entry, not reuse the popped one",
        );
        // The pre-IRQ PC pushed this round is the post-RETFIE
        // 0x0042 (the firmware was about to fetch its next
        // instruction at the restored PC when the still-
        // pending IRQ fired).
        assert_eq!(stack.top(), 0x0042);
    }

    /// `restore_gie_on_retfie`: in IPEN=0 mode, RETFIE sets
    /// GIE only (PEIE untouched).
    #[test]
    fn restore_gie_on_retfie_ipen0_sets_gie_only() {
        let mut mem = fresh_mem();
        // IPEN=0 (RCON.bit7 clear), GIE clear, PEIE clear.
        mem.write_raw(Address::from_raw(RCON_ADDR), 0);
        mem.write_raw(Address::from_raw(INTCON_ADDR), 0);
        restore_gie_on_retfie(&mut mem, Some(IrqContext::Compatibility));
        let intcon = mem.read_raw(Address::from_raw(INTCON_ADDR));
        assert_eq!(intcon & INTCON_GIE_GIEH, INTCON_GIE_GIEH);
        assert_eq!(intcon & INTCON_PEIE_GIEL, 0);
    }

    /// `restore_gie_on_retfie`: in IPEN=1 mode, RETFIE sets
    /// both GIEH and GIEL (Phase-3.5 simplification per
    /// docstring; precise high-vs-low fast-stack semantics
    /// land with task #15).
    #[test]
    fn restore_gie_on_retfie_ipen1_sets_both_gates() {
        let mut mem = fresh_mem();
        mem.write_raw(Address::from_raw(RCON_ADDR), RCON_IPEN);
        mem.write_raw(Address::from_raw(INTCON_ADDR), 0);
        restore_gie_on_retfie(&mut mem, None);
        let intcon = mem.read_raw(Address::from_raw(INTCON_ADDR));
        assert_eq!(intcon & INTCON_GIE_GIEH, INTCON_GIE_GIEH);
        assert_eq!(intcon & INTCON_PEIE_GIEL, INTCON_PEIE_GIEL);
    }

    /// IRQ dispatch where the return-PC push is THE filling
    /// push (depth 30->31, STKFUL transition 0->1) + STVREN=1
    /// must fire a hardware reset instead of vectoring.  Codex
    /// review of 2fa7d0a MEDIUM 3 + 41d6195 MEDIUM (trigger
    /// is the FILLING push per DS39632E §5.1.2.4).
    #[test]
    fn irq_dispatch_overflow_with_stvren_triggers_reset() {
        let mut core = Core::new(Variant::Pic18F25K20);
        // STVREN=1: CONFIG4L bit 0.  Config bytes start at
        // raw[0x300000] with CONFIG4L at byte index 6.
        let mut cfg = [0u8; 14];
        cfg[6] = 0x01;
        core.config = crate::config::Config::from_bytes(cfg);
        // Pre-fill to depth=30: the IRQ's return-PC push
        // will take depth 30->31 and latch STKFUL, which
        // is the documented reset trigger.
        let mut stack = Stack::new();
        for _ in 0..30 {
            assert!(stack.push(0x1000));
        }
        assert_eq!(stack.depth(), 30);
        assert!(!stack.overflow(), "pre: STKFUL clear at depth=30");
        // INT0 pending+enabled, GIE set.
        core.set_pc(0x0042);
        core.memory.write_raw(
            Address::from_raw(INTCON_ADDR),
            INTCON_GIE_GIEH | 0x10 | 0x02,
        );
        let cycles = try_dispatch_irq(&mut core, &mut stack);
        assert_eq!(cycles, Some(2));
        // Reset post-conditions: PC=0, stack depth=0, STKFUL
        // latched, INTCON.GIE cleared by Tbl 4-4 column 6 SFR
        // reset (HIGH from 41d6195 review).
        assert_eq!(core.pc(), 0, "reset must preempt vector entry");
        assert_eq!(stack.depth(), 0, "stack depth=0 after reset");
        assert!(stack.overflow(), "STKFUL stays latched across reset");
        let intcon = core.memory.read_raw(Address::from_raw(INTCON_ADDR));
        assert_eq!(
            intcon & 0xFE,
            0,
            "INTCON bits 7..1 must clear on Tbl 4-4 col-6 reset \
             so the next step does not re-vector immediately"
        );
        // SFR mirrors must be re-mirrored AFTER the reset:
        // STKPTR depth field = 0.
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xFFC)) & 0x1F,
            0,
            "STKPTR mirror must be 0 after reset"
        );
    }

    /// IRQ dispatch where the return-PC push fills the stack
    /// (depth 30->31) but STVREN=0 must vector normally
    /// (latch STKFUL but NOT reset).
    #[test]
    fn irq_dispatch_overflow_with_stvren_clear_latches_only() {
        let mut core = Core::new(Variant::Pic18F25K20);
        // STVREN=0 (default Config::from_bytes([0;14])).
        let mut stack = Stack::new();
        for _ in 0..30 {
            assert!(stack.push(0x1000));
        }
        core.set_pc(0x0042);
        core.memory.write_raw(
            Address::from_raw(INTCON_ADDR),
            INTCON_GIE_GIEH | 0x10 | 0x02,
        );
        let cycles = try_dispatch_irq(&mut core, &mut stack);
        assert_eq!(cycles, Some(2));
        // No reset: PC = vector, depth=31 (filling push
        // accepted), STKFUL latched.
        assert_eq!(core.pc(), IRQ_VECTOR_HIGH, "STVREN=0 must vector normally");
        assert_eq!(stack.depth(), 31, "filling push reaches depth=31");
        assert!(stack.overflow(), "STKFUL latched on filling push regardless of STVREN");
    }
}
