//! PIC18 reset-source dispatcher.
//!
//! Each documented reset source (POR, BOR, MCLR, WDT, RESET
//! instruction, stack overflow / underflow with STVREN=1) sets
//! a different combination of bits in RCON / STKPTR per
//! DS39632E Table 4-1 ("Status Bits, Their Significance and the
//! Initialization Conditions for RCON Register") and §5.4.2
//! ("Stack Full and Underflow Resets").  This module's job is
//! to take a [`ResetSource`] and a `&mut Core` + `&mut Stack`
//! and apply the right state transition; whether to actually
//! reset (e.g. stack overflow only resets when STVREN=1) is the
//! caller's responsibility (the executor in P1.2 dispatch +
//! P1.7 config-bit parser determine STVREN).
//!
//! ### What this module does NOT do
//!
//! * It does NOT apply the configuration words.  CONFIG bits
//!   like STVREN, BOREN, IPEN, WDTEN are parsed in P1.7; the
//!   reset path consumes them as preconditions.
//! * It does NOT model power-down (Sleep) or oscillator
//!   start-up timers.  Those belong to the oscillator
//!   peripheral (P2.9).
//! * It does NOT model SFRs that depend on dynamic device state
//!   the reset path has no way to know (e.g. OSCCON's IOFS bit
//!   that flips once HFINTOSC stabilises -- a few hundred Tcy
//!   after POR per DS40001303H §2.5.2.1).  Those are P2 work.
//!
//! ### What this module DOES do (extended in P1.8d / P2.1)
//!
//! POR programs the SFR window with the full K20 power-on
//! initial values per DS40001303H Table 4-4 p.56-60.  BOR
//! and MCLR/WDT/RESET use distinct strategies:
//!
//!   * **POR**: data-memory wipe + RCON-rewrite +
//!     `apply_por_sfr_defaults` (variant-aware K20_POR
//!     non-zero defaults).
//!   * **BOR**: SFR-window wipe (0xF60..0xFFF only) +
//!     `apply_por_sfr_defaults` + RCON-rewrite.  GPRs
//!     preserved per §4.4.
//!   * **MCLR/WDT/RESET-instruction**: per-SFR enumeration
//!     (`apply_k20_mclr_zero_sfrs` for the fully-zero MCLR
//!     rows, `apply_k20_mclr_rmw_sfrs` for the mixed
//!     preserved/fixed-bit rows) +
//!     `apply_por_sfr_defaults` on top.  GPRs preserved.
//!
//! 2455 has TARGETED POR/BOR defaults (task #30):
//! `apply_2455_por_sfr_defaults` covers TXSTA.TRMT (the
//! boot-critical one -- without it V3.1's wait_trmt_bounded
//! times out and `hard_reset` reboots forever) plus
//! INTCONn / T0CON / PR2 / BAUDCON / IPRn rounded out for
//! symmetry with the K20 table.
//! The broader 2455 SFR table (OSCCON / HLVDCON / TRISx
//! / CCP / SPP / USB / etc.) and the 2455 MCLR zero/RMW
//! lists still land alongside the V2.3 MAIN parity gate
//! (P1.8e); 2455 stack-fault has its own targeted
//! `apply_2455_mclr_irq_sfrs` (task #31).

use crate::config::{Config, FoscMode};
use crate::core::Core;
use crate::memory::{Address, Variant};
use crate::stack::Stack;
use serde::{Deserialize, Serialize};

/// `RCON` SFR address on both PIC18 variants.
pub const RCON_ADDR: u16 = 0xFD0;

/// `RCON.RI` (RESET Instruction Flag), bit 4.  `0` = the RESET
/// instruction last fired; `1` otherwise.
pub const RCON_RI: u8 = 0x10;

/// `RCON.TO` (Watchdog Time-out Flag), bit 3.  `0` = WDT
/// timed out; `1` otherwise.
pub const RCON_TO: u8 = 0x08;

/// `RCON.PD` (Power-down Detection Flag), bit 2.  `0` = SLEEP
/// instruction last executed; `1` otherwise.
pub const RCON_PD: u8 = 0x04;

/// `RCON.POR` (Power-on Reset Flag), bit 1.  `0` = POR fired
/// since the last software-set; `1` otherwise.  Cleared only
/// by POR; reasserted by software.
pub const RCON_POR: u8 = 0x02;

/// `RCON.BOR` (Brown-out Reset Flag), bit 0.  `0` = BOR fired
/// since the last software-set; `1` otherwise.  Cleared only by
/// BOR (or POR via config); reasserted by software.
pub const RCON_BOR: u8 = 0x01;

/// What initiated this reset.  Drives the RCON / STKPTR bit
/// transitions per DS39632E Table 4-1.
#[derive(Serialize, Deserialize, Copy, Clone, Eq, PartialEq, Debug, Hash)]
pub enum ResetSource {
    /// Power-On Reset.  Applies the strictest POR state: clears
    /// RCON.POR and RCON.BOR, sets RI/TO/PD high, clears the
    /// stack and its sticky flags, and zeros all 4096 bytes of
    /// data memory before the reset vector fires.
    PowerOn,
    /// Brown-out Reset.  Same RCON updates as POR except
    /// RCON.POR is preserved; STKFUL/STKUNF preserved (DS39632E
    /// §5.4.2 says STKFUL is cleared only by POR).
    BrownOut,
    /// External MCLR.  RCON.TO is forced to 1; other RCON bits
    /// preserved.  Stack pointer is reset to 0 per DS39632E
    /// §5.4 ("On Reset, the Stack Pointer value will be zero")
    /// while sticky flags STKFUL/STKUNF and slot data are
    /// preserved (Table 4-1: STKFUL=u, STKUNF=u for MCLR).
    Mclr,
    /// Watchdog Time-out reset (not the wake-from-sleep case;
    /// see DS39632E §25.2).  RCON.TO forced to 0; other bits
    /// preserved.  Stack pointer reset to 0; flags + slot data
    /// preserved (same as MCLR).
    Wdt,
    /// `RESET` instruction.  RCON.RI forced to 0; other bits
    /// preserved.  Stack pointer reset to 0; flags + slot data
    /// preserved (same as MCLR).
    ResetInstruction,
    /// Stack Full Reset, fires only when STVREN=1 and a CALL/
    /// RCALL/interrupt push fills the 31st slot.  STKPTR depth
    /// is forced to 0; STKFUL stays set (per DS39632E §5.4.2).
    /// RCON unchanged.
    StackFull,
    /// Stack Underflow Reset, fires only when STVREN=1 and a
    /// RETURN/RETFIE/POP is issued at depth=0.  STKUNF stays
    /// set.  RCON unchanged.
    StackUnderflow,
}

/// Apply a reset.  Mutates `core` and `stack` to the post-reset
/// state documented in DS39632E Table 4-1 + §5.4.2.
///
/// PC is set to the reset vector (0x0000) for every reset type;
/// see DS39632E §4.0.  The caller is then expected to start
/// executing from there on the next instruction-fetch cycle.
pub fn apply_reset(core: &mut Core, stack: &mut Stack, source: ResetSource) {
    // PC always returns to the reset vector.  DS39632E §4.0:
    // "Reset events vector all PIC18 devices back to address
    // 0000h, where execution restarts."
    core.set_pc(0);
    core.tblwt_holding.fill(0xFF);
    core.reset_power_state();

    // Drop every peripheral's internal state.  Has to happen
    // *before* the SFR rewrite below: if a peripheral's
    // tick_tcy were called between the SFR wipe and a peripheral
    // reset (e.g. via a stray advance_cycles in a test harness),
    // the stale TSR shifter could still mutate the freshly-POR'd
    // PIR1.TXIF / TXSTA.TRMT.  Clearing peripheral state here
    // makes the reset path order-independent.
    core.peripherals.reset_state();

    let rcon = core.memory.read_raw(Address::from_raw(RCON_ADDR));
    let rcon = match source {
        // POR: RI=1, TO=1, PD=1, POR=0, BOR=0.
        ResetSource::PowerOn => (rcon & !(RCON_POR | RCON_BOR)) | RCON_RI | RCON_TO | RCON_PD,
        // BOR: RI=1, TO=1, PD=1, POR=u, BOR=0.
        ResetSource::BrownOut => (rcon & !RCON_BOR) | RCON_RI | RCON_TO | RCON_PD,
        // MCLR: RI=u, TO=1, PD=u, POR=u, BOR=u.
        ResetSource::Mclr => rcon | RCON_TO,
        // WDT: TO=0, others u.  (This is the WDT-while-running
        // reset; the WDT-during-Sleep wake-up clears PD too,
        // which the executor handles separately in P1.7.)
        ResetSource::Wdt => rcon & !RCON_TO,
        // RESET instruction: RI=0, others u.
        ResetSource::ResetInstruction => rcon & !RCON_RI,
        // Stack overflow / underflow: RCON unchanged; only
        // STKPTR latches change.
        ResetSource::StackFull | ResetSource::StackUnderflow => rcon,
    };
    core.memory.write_raw(Address::from_raw(RCON_ADDR), rcon);

    // Stack / STKPTR transitions.
    match source {
        ResetSource::PowerOn => {
            // Full stack wipe: depth=0, slots zeroed, both
            // sticky flags cleared.
            stack.por_reset();
            // POR also zeroes ALL data memory — even though
            // that's nominally a peripheral concern, the reset
            // module owns the "everything is zero on day one"
            // contract because no peripheral has run yet.
            for byte in core.memory.as_mut_slice() {
                *byte = 0;
            }
            // RCON's POR-reset value still needs to be written
            // back: clearing the slice above blew away the
            // bits we just composed.  Re-write RCON to the
            // post-POR state so RI/TO/PD/POR/BOR are correct.
            core.memory
                .write_raw(Address::from_raw(RCON_ADDR), RCON_RI | RCON_TO | RCON_PD);
            // SFR POR initialisation table (variant-specific).
            apply_por_sfr_defaults(core);
        }
        ResetSource::BrownOut => {
            // DS39632E §5.4 ("On Reset, the Stack Pointer
            // value will be zero") + Table 4-1 (STKFUL=u,
            // STKUNF=u for all of these): the pointer drops
            // to 0 on these resets, but the sticky flags AND
            // the slot data are preserved across the reset.
            stack.reset_pointer_preserve_flags();
            // BOR shares Tbl 4-4's "Power-on Reset, Brown-out
            // Reset" column.  That column has NO `u`
            // (preserved) entries -- only `0`, `1`, `x`, and
            // `q`, all of which our model treats as 0 unless
            // explicitly listed in K20_POR with a fixed
            // value.  Accordingly: wipe the entire SFR
            // window 0xF60..0xFFF first, then re-apply
            // K20_POR for the non-zero fixed defaults.  GPRs
            // (data memory below 0xF60) ARE preserved across
            // BOR per §4.4 -- only POR wipes RAM.
            //
            // This blanket SFR wipe replaces the previous
            // per-SFR list approach: by definition every
            // SFR's BOR value is "0 or whatever K20_POR
            // says", so wipe + table is correct by
            // construction and avoids the per-SFR
            // enumeration drift hazard codex flagged.
            wipe_sfr_window(core);
            apply_por_sfr_defaults(core);
            // RCON's POR-state was already composed at the
            // top of apply_reset (see the `rcon` match
            // earlier).  The SFR wipe above blew it away;
            // re-write the composed RCON value back so
            // RI/TO/PD/POR/BOR are consistent.  (POR's
            // memory-wipe path does the same dance.)
            core.memory.write_raw(Address::from_raw(RCON_ADDR), rcon);
        }
        ResetSource::Mclr | ResetSource::Wdt | ResetSource::ResetInstruction => {
            // DS39632E §5.4 + Table 4-1: STKPTR depth → 0;
            // sticky flags + slot data preserved.  A previous
            // CALL/RCALL push remains in slot[depth_pre-1] and
            // can be read via TOSU/H/L after firmware writes a
            // new depth into STKPTR.
            stack.reset_pointer_preserve_flags();
            // Tbl 4-4 column-2 "MCLR Resets, WDT Reset, RESET
            // Instruction, Stack Resets" has a mix of fixed
            // values, `u` preserved bits, and `x` unknowns
            // (treated as 0).  Data memory (GPRs) IS preserved
            // across these resets -- only POR wipes RAM -- so
            // we cannot use the BOR-style blanket SFR-window
            // wipe.  Three passes per K20:
            //   (1) zero the SFRs whose MCLR row is fully zero
            //       (`apply_k20_mclr_zero_sfrs`).
            //   (2) RMW the SFRs whose MCLR row mixes fixed
            //       and preserved (`u`) bits
            //       (`apply_k20_mclr_rmw_sfrs` -- INTCON,
            //       T1CON, EECON1, PORTA/B/E).
            //   (3) re-apply K20_POR for the non-zero fixed
            //       defaults (INTCON2 = 0xF5, T0CON = 0xFF,
            //       PR2 = 0xFF, etc. -- every entry has the
            //       same value in the POR/BOR column and the
            //       MCLR-style column).
            // SFRs whose MCLR row is all-`u` (T3CON, STATUS,
            // timers, ADRES, CCPR, FSR{0..2}L, WREG, PRODL/H,
            // SSPBUF, PORTC, LATA-C) are MCLR no-ops and don't
            // need an entry in either pass.
            match core.variant() {
                Variant::Pic18F25K20 => {
                    apply_k20_mclr_zero_sfrs(core);
                    apply_k20_mclr_rmw_sfrs(core);
                }
                Variant::Pic18F2455 => {
                    apply_2455_mclr_zero_sfrs(core);
                    apply_2455_mclr_rmw_sfrs(core);
                }
            }
            apply_por_sfr_defaults(core);
        }
        ResetSource::StackFull => {
            // Depth -> 0; STKFUL stays set (latched).  Slot
            // data preserved.  Per DS39632E Tbl 4-4 column 6
            // ("MCLR Resets, WDT Reset, RESET Instruction,
            // Stack Resets") the SFR window resets to the
            // same MCLR-style state as the other entries in
            // the column -- in particular INTCON clears
            // (0000 000u), so the very next `step()` after
            // an IRQ-induced stack-full reset cannot
            // immediately re-vector into 0x0008.
            stack.reset_for_stack_full();
            apply_stack_fault_sfr_reset(core);
        }
        ResetSource::StackUnderflow => {
            // Depth stays 0; STKUNF latches.  Same Tbl 4-4
            // column-6 SFR reset as StackFull.
            stack.reset_for_stack_underflow();
            apply_stack_fault_sfr_reset(core);
        }
    }

    // Post-SFR-reset peripheral sync.  Each peripheral that
    // keeps an internal shadow of an SFR byte (e.g. Timer3's
    // RD16-aware tmr3h_live) refreshes from the now-canonical
    // SFR memory.  Stack resets now also touch SFR memory
    // (per Tbl 4-4 column 6), so they sync alongside the
    // MCLR-style group.
    core.peripherals.sync_from_memory(&mut core.memory);
}

/// Zero every byte in the SFR window 0xF60..0xFFF without
/// touching the GPR area below.  Used by the BOR arm to
/// implement Tbl 4-4's "every SFR resets to a fixed value
/// or `x`" POR/BOR semantic without enumerating every SFR
/// individually.  The caller is expected to follow up with
/// [`apply_por_sfr_defaults`] (and re-write RCON) so SFRs
/// with non-zero POR-column values land at the right bytes.
fn wipe_sfr_window(core: &mut Core) {
    for addr in 0xF60u16..=0xFFF {
        core.memory.write_raw(Address::from_raw(addr), 0);
    }
}

/// Apply the variant-specific SFR power-on initial values.
/// Runs after the POR memory wipe, so any non-zero default the
/// silicon brings up at POR is restored.
///
/// K20: DS40001303H Table 4-4 ("Initialization Conditions for All
/// Registers", p.56-60) + Table 5-2 footnotes for 28-pin masking.
/// Full coverage of every non-zero POR default.
///
/// 2455: TARGETED coverage from task #30 -- TXSTA.TRMT (the
/// boot-critical one) plus INTCONn / T0CON / PR2 / BAUDCON /
/// IPRn rounded out for symmetry with the K20 table.  Driven by
/// `apply_2455_por_sfr_defaults`.  See its docstring for the
/// boot-dependency rationale.  The remaining 2455 defaults
/// (OSCCON / HLVDCON / TRISx / CCP / SPP / USB / etc.) land
/// alongside the V2.3 MAIN parity gate (P1.8e).
///
/// **Known gap (scoped):**
///   * On BOR a 2455 core wipes the SFR window via the BOR
///     arm and then re-applies POR defaults -- the targeted
///     2455 set above is now restored, but the K20-only
///     entries (TRISx / OSCCON / etc.) stay zero.
///   * On MCLR/WDT/RESET a 2455 core preserves whatever SFR
///     bytes existed pre-reset because the MCLR zero/RMW
///     lists are K20-only.  The 2455 stack-fault path goes
///     through `apply_2455_mclr_irq_sfrs` (task #31) which
///     covers the IRQ subset only.
/// The current Phase-2 parity test suite does not exercise
/// any 2455 MCLR / WDT / RESET-instruction reset path, so
/// the gap is bounded.  The V2.3 MAIN parity gate landing
/// later will add the 2455 K20-equivalent zero/RMW lists.
fn apply_por_sfr_defaults(core: &mut Core) {
    match core.variant() {
        Variant::Pic18F25K20 => apply_k20_por_sfr_defaults(core),
        Variant::Pic18F2455 => apply_2455_por_sfr_defaults(core),
    }
}

/// PIC18F2455 POR/BOR SFR initial values, narrow scope.
///
/// Source: DS39632E Tbl 4-4 (p.53-57).  This is a TARGETED
/// subset, not the full 2455 POR table -- the broader
/// rewrite lands with the V2.3 MAIN parity gate (P1.8e).
/// Coverage scope: TXSTA.TRMT (the boot-critical one) plus
/// the remaining INTCONn / T0CON / PR2 / BAUDCON / IPRn
/// non-zero defaults rounded out for symmetry with the
/// K20 table -- so the 2455 reset side stays close to its
/// K20 cousin even though only TRMT is currently
/// load-bearing for V3.1 boot.
///
/// Coverage rationale (task #30 root-cause): V3.1 MAIN's
/// boot path calls `wait_trmt_bounded` which polls
/// TXSTA.TRMT.  TRMT's POR value is 1 (TSR idle); without
/// this seeding, our SFR wipe leaves TRMT=0 and the wait
/// times out, the firmware hits `hard_reset` (RESET
/// instruction), and reboots in an infinite loop, never
/// reaching the chain protocol parser.  FID-07 broadened this
/// table to cover the previously deferred 2455 OSCCON/HLVDCON,
/// TRIS, comparator, and USB reset-default rows that are visible
/// before the MAIN firmware touches those peripherals.
fn apply_2455_por_sfr_defaults(core: &mut Core) {
    const POR_2455: &[(u16, u8, &str)] = &[
        // INTCON2: RBPU=1, INTEDG0/1/2=1, TMR0IP=1, RBIP=1.
        // Bits 3 and 1 unimplemented.  Per Tbl 4-4 row.
        (0xFF1, 0xF5, "INTCON2"),
        // INTCON3: INT2IP=1, INT1IP=1.  Bits 5 and 2
        // unimplemented.
        (0xFF0, 0xC0, "INTCON3"),
        // T0CON: all 1s at POR (timer disabled, max prescaler).
        (0xFD5, 0xFF, "T0CON"),
        // OSCCON: 0100 q000; q status/SCS bits use deterministic
        // zero until the oscillator peripheral changes them.
        (0xFD3, 0x40, "OSCCON"),
        // HLVDCON: HLVDL<3:0>=0101, bit 6 unimplemented.
        (0xFD2, 0x05, "HLVDCON"),
        // PR2: Timer2 period match value = 0xFF.  Address
        // 0xFCB per DS39632E Tbl 5-1 (NOT 0xFAB -- that's
        // RCSTA, whose POR value is `0000 000x` and stays
        // zeroed by the SFR-window wipe).
        (0xFCB, 0xFF, "PR2"),
        // TXSTA: TRMT=1 (TSR empty).  TRMT is hardware-driven
        // read-only; the SFR write mask in exec.rs preserves
        // it across SW writes -- so without seeding it here
        // the firmware's wait_trmt_bounded poll never observes
        // TRMT=1 and times out.  Task #30 root-cause.
        (0xFAC, 0x02, "TXSTA"),
        // BAUDCON: RCIDL=1 (receiver idle).  Bit 2 unimpl.
        (0xFB8, 0x40, "BAUDCON"),
        // CMCON: comparator module POR value 0000 0111.
        (0xFB4, 0x07, "CMCON"),
        // IPR1: all peripheral interrupt priorities high.
        // PIC18F2455 (28-pin) has SPPIP (bit 7) unimplemented
        // per DS Tbl 4-4 second row + footnote 3 -> 0x7F.
        (0xF9F, 0x7F, "IPR1"),
        // IPR2: all bits 1.
        (0xFA2, 0xFF, "IPR2"),
        // TRISC: 11-- -111; RC5/RC4 are USB pins, bit 3 is
        // unimplemented on 28-pin 2455.
        (0xF94, 0xC7, "TRISC"),
        // TRISB: all input.
        (0xF93, 0xFF, "TRISB"),
    ];
    for &(addr, value, _name) in POR_2455 {
        core.memory.write_raw(Address::from_raw(addr), value);
    }
    core.memory
        .write_raw(Address::from_raw(0xF92), trisa_por_value_2455(&core.config));
}

fn trisa_por_value_k20(config: &Config) -> u8 {
    if fosc_exposes_ra6_as_port(config.fosc()) {
        0x7F
    } else {
        0x3F
    }
}

fn trisa_por_value_2455(config: &Config) -> u8 {
    let mut value = 0x3F;
    if fosc_exposes_ra6_as_port(config.fosc()) {
        value |= 0x40;
    }
    value
}

fn fosc_exposes_ra6_as_port(fosc: FoscMode) -> bool {
    matches!(fosc, FoscMode::ECIO | FoscMode::ECPIO | FoscMode::INTIO)
}

/// Apply the Tbl 4-4 column-6 SFR reset for stack-fault
/// (StackFull / StackUnderflow) resets.  Shared between
/// the two arms.
///
/// On K20 this delegates to the full MCLR-style reset
/// machinery -- zero SFRs, RMW SFRs, POR fixed defaults,
/// covering INTCON / PIE1 / PIR1 / PIE2 / PIR2 etc.
///
/// On 2455 this now uses the FID-07 MCLR/WDT/RESET table
/// too; earlier revisions only cleared the IRQ subset.
fn apply_stack_fault_sfr_reset(core: &mut Core) {
    match core.variant() {
        Variant::Pic18F25K20 => {
            apply_k20_mclr_zero_sfrs(core);
            apply_k20_mclr_rmw_sfrs(core);
            apply_por_sfr_defaults(core);
        }
        Variant::Pic18F2455 => {
            apply_2455_mclr_zero_sfrs(core);
            apply_2455_mclr_rmw_sfrs(core);
            apply_por_sfr_defaults(core);
        }
    }
}

fn apply_2455_mclr_zero_sfrs(core: &mut Core) {
    const ZERO_SFRS: &[u16] = &[
        0xFEA, // FSR0H
        0xFE2, // FSR1H
        0xFDA, // FSR2H
        0xFE0, // BSR
        0xFD7, // TMR0H
        0xFD1, // WDTCON
        0xFCC, // TMR2
        0xFCA, // T2CON
        0xFC8, // SSPADD
        0xFC7, // SSPSTAT
        0xFC6, // SSPCON1
        0xFC5, // SSPCON2
        0xFC2, // ADCON0
        0xFC1, // ADCON1
        0xFC0, // ADCON2
        0xFBA, // CCP2CON
        0xFB6, // ECCP1DEL
        0xFB5, // ECCP1AS
        0xFB3, // T3CON
        0xFB0, // SPBRGH
        0xFAF, // SPBRG
        0xFAE, // RCREG
        0xFAD, // TXREG
        0xFAB, // RCSTA
        0xFA9, // EEADR
        0xFA8, // EEDATA
        0xFA6, // EECON1
        0xFA0, // PIE2
        0xFA1, // PIR2
        0xF9D, // PIE1
        0xF9E, // PIR1
        0xF9B, // OSCTUNE
        0xFF9, // PCL
        0xFFA, // PCLATH
        0xFFB, // PCLATU
        0xFF6, // TBLPTRL
        0xFF7, // TBLPTRH
        0xFF8, // TBLPTRU
        0xFF5, // TABLAT
    ];
    for &addr in ZERO_SFRS {
        core.memory.write_raw(Address::from_raw(addr), 0);
    }
    // USB-SIE reset rows (DS39632E Tbl 4-4): UEP0..15, UCFG,
    // UADDR, UCON, USTAT, UEIE, UEIR, UIE, UIR, UFRMH, UFRML
    // all reset to zero under MCLR/WDT/RESET/stack resets.
    for addr in 0xF66u16..=0xF7F {
        core.memory.write_raw(Address::from_raw(addr), 0);
    }
}

fn apply_2455_mclr_rmw_sfrs(core: &mut Core) {
    const RMW: &[(u16, u8, u8)] = &[
        // INTCON: bits 7..1 reset, RBIF bit 0 preserved.
        (0xFF2, 0x00, 0xFE),
        // T1CON: T1RUN bit 6 resets; other bits preserved.
        (0xFCD, 0x00, 0x40),
        // EECON1: EEPGD/CFGS/FREE/WRERR/WREN/WR/RD reset,
        // unimplemented bit 5 remains 0; only x/u bits outside
        // reset_mask would be preserved.
        (0xFA6, 0x00, 0xDF),
        // PORTA: preserve RA6 and RA4 latch/read bits; clear
        // RA7 (unimplemented on 28-pin 2455), RA5, and RA3..RA0.
        (0xF80, 0x00, 0xAF),
        // PORTE: preserve RE3, clear RE2..RE0.
        (0xF84, 0x00, 0x07),
    ];
    for &(addr, target, reset_mask) in RMW {
        let cur = core.memory.read_raw(Address::from_raw(addr));
        let next = (cur & !reset_mask) | (target & reset_mask);
        core.memory.write_raw(Address::from_raw(addr), next);
    }
}

/// PIC18F25K20 POR/BOR SFR initial values.
///
/// Source: DS40001303H Table 4-4 (p.56-60).  Each entry is
/// `(addr, value)` where `value` is the post-POR byte after
/// applying any 28-pin / oscillator-mode footnote masks
/// documented in Table 5-2 footnotes 2 and 5.
///
/// Where Table 4-4 lists `xxxx xxxx` (unknown / undefined) the
/// register is omitted -- the POR memory wipe leaves it 0,
/// which is what gpsim's K20 model also reports.
fn apply_k20_por_sfr_defaults(core: &mut Core) {
    // (addr, por_value, datasheet_note)
    //
    // Bit-pattern translation rules:
    //   * `1` bit  -> 1 in the byte
    //   * `0` bit  -> 0
    //   * `-` bit  -> 0  (unimplemented; reads as 0 per legend)
    //   * `q` bit  -> 0  (condition-dependent; the post-POR
    //                     value is 0 for the bits relevant here;
    //                     OSCCON's IOFS/SCS bits stay 0 until
    //                     HFINTOSC stabilises -- a P2 concern)
    const K20_POR: &[(u16, u8)] = &[
        // INTCON2: RBPU=1, INTEDG0/1/2=1, TMR0IP=1, RBIP=1.
        // Bits 3 (-) and 1 (-) unimplemented -> 0.
        (0xFF1, 0xF5),
        // INTCON3: INT2IP=1, INT1IP=1, others 0.  Bits 5 (-) and
        // 2 (-) unimplemented.
        (0xFF0, 0xC0),
        // T0CON: all 1s at POR (timer disabled, prescaler maxed).
        (0xFD5, 0xFF),
        // OSCCON: IRCF<2:0>=011 (1 MHz nominal HFINTOSC tap).
        // OSTS/IOFS/SCS<1:0> are q-bits and stay 0 until the
        // oscillator-stabilisation timer fires -- modelled in
        // P2's oscillator peripheral, not here.  gpsim's K20
        // ships its base-class initial value 0x40
        // (vendor/gpsim-0.32.1-xtc/src/16bit-processors.cc:560
        // `add_sfr_register(osccon, 0xfd3, RegisterValue(0x40,
        // 0))`) and the K20 subclass does not override that
        // entry for OSCCON.  Documented as a known static
        // divergence (rust=0x30, gpsim=0x40) in the parity
        // test's GPSIM_K20_DEVIATIONS table.
        (0xFD3, 0x30),
        // HLVDCON: HLVDL<3:0>=0101 (default HLV detect = 2.0V
        // typical per Reg 21-1).  Bit 6 (-) unimplemented.
        (0xFD2, 0x05),
        // PR2: Timer2 period match value = 0xFF.
        (0xFCB, 0xFF),
        // TXSTA: TRMT=1 (TSR empty).  TRMT is hardware-driven
        // read-only; the SFR write mask in exec.rs preserves it
        // across SW writes.
        (0xFAC, 0x02),
        // PSTRCON: STRA=1 (single-output PWM steered to P1A).
        // Bits 7..4 (-) unimplemented; STRSYNC bit 4 = 0.
        (0xFB9, 0x01),
        // BAUDCON: RCIDL=1 (receiver idle).  Bit 2 (-) unimpl.
        (0xFB8, 0x40),
        // IPR1: all peripheral interrupt priorities high (=1).
        // PIC18F2XK20 (28-pin) has bit 7 (PSPIP) unimplemented
        // per Table 5-2 footnote 2 -> 0x7F not 0xFF.
        (0xF9F, 0x7F),
        // IPR2: all bits 1.
        (0xFA2, 0xFF),
        // TRISB: all-input.
        (0xF93, 0xFF),
        // TRISC: all-input.
        (0xF94, 0xFF),
        // ANSEL: all-analog on the bits the silicon implements.
        // Table 5-2 footnote 2 marks ANS5/6/7 unimplemented on
        // 28-pin (PIC18F2XK20) -- they read as 0 -- so the
        // effective POR is 0x1F, not the 0xFF shown for the
        // 40/44-pin family.  gpsim's K20 model misses this
        // footnote and brings ANSEL up at 0xFF; the parity test
        // exempts the resulting (rust=0x1F, gpsim=0xFF) cell.
        (0xF7E, 0x1F),
        // WPUB: weak pull-ups enabled.
        (0xF7C, 0xFF),
        // SLRCON: slew-rate control = normal (1) for SLRA/B/C.
        // 28-pin omits SLRD/SLRE per Table 5-2 footnote 2 -> 0x07.
        (0xF78, 0x07),
        // SSPMSK: I2C address mask = all 1s.
        (0xF77, 0xFF),
    ];

    for (addr, value) in K20_POR {
        core.memory.write_raw(Address::from_raw(*addr), *value);
    }
    // CONFIG-dependent `q` rows from DS40001303H Table 4-4 /
    // Table 5-2 footnotes.  FID-07 intentionally moves these out
    // of the gpsim-compat static table: V1.71's FOSC=XT disables
    // RA6/RA7 as PORTA pins (TRISA=0x3F), and PBADEN=0 makes
    // ANSELH reset to zero.
    core.memory
        .write_raw(Address::from_raw(0xF92), trisa_por_value_k20(&core.config));
    core.memory.write_raw(
        Address::from_raw(0xF7F),
        if core.config.pbaden() { 0x1F } else { 0x00 },
    );
}

/// SFRs that reset to a fully-zero byte on every K20 reset
/// source whose Tbl 4-4 column-2 ("MCLR Resets, WDT Reset,
/// RESET Instruction, Stack Resets") AND column-1 ("Power-on
/// Reset, Brown-out Reset") are both fully-zero.
///
/// POR clears these implicitly via the data-memory wipe in
/// `apply_reset`'s POR arm; non-POR resets and BOR don't
/// wipe RAM, so we zero these SFRs explicitly.
///
/// SFRs whose MCLR-column value mixes preserved (`u`) bits
/// with fixed bits (INTCON, T1CON, EECON1, PORTA/B/E) are
/// NOT in this list -- they live in
/// `apply_k20_mclr_rmw_sfrs` and use RMW-style per-bit
/// handling.  SFRs whose MCLR row is fully `u` (T3CON,
/// STATUS, the timer / ADRES / CCPR / FSR-low / WREG /
/// PROD / SSPBUF / PORTC / LATx data registers) are MCLR
/// no-ops and don't need an entry anywhere -- the BOR
/// path's SFR-window wipe handles their POR/BOR-side `x`-
/// as-0 reset.
fn apply_k20_mclr_zero_sfrs(core: &mut Core) {
    const K20_MCLR_ZERO_SFRS: &[u16] = &[
        0xF79, // CM2CON1
        0xF7A, // CM2CON0
        0xF7B, // CM1CON0
        0xF7D, // IOCB
        0xF9B, // OSCTUNE
        0xF9D, // PIE1
        0xF9E, // PIR1
        0xFA0, // PIE2
        0xFA1, // PIR2
        0xFA8, // EEDATA
        0xFA9, // EEADR
        0xFAA, // EEADRH (PIC18F26K20-only; harmless on 25K20)
        0xFAB, // RCSTA  (POR/MCLR `0000 000x`; `x`-as-0 -> 0)
        0xFAD, // TXREG
        0xFAE, // RCREG
        0xFAF, // SPBRG
        0xFB0, // SPBRGH
        0xFB4, // CVRCON2
        0xFB5, // CVRCON
        0xFB6, // ECCP1AS
        0xFB7, // PWM1CON
        0xFBA, // CCP2CON  (POR `--00 0000` = 0)
        0xFBD, // CCP1CON
        0xFC0, // ADCON2  (POR `0-00 0000` = 0)
        0xFC1, // ADCON1  (POR `--00 0qqq`; conservative 0)
        0xFC2, // ADCON0  (POR `--00 0000` = 0)
        0xFC5, // SSPCON2
        0xFC6, // SSPCON1
        0xFC7, // SSPSTAT
        0xFC8, // SSPADD
        0xFCA, // T2CON  (POR `-000 0000` = 0)
        0xFCC, // TMR2
        0xFD1, // WDTCON  (POR `---- ---0` = 0)
        0xFD7, // TMR0H
        0xFDA, // FSR2H  (POR `---- 0000` = 0)
        0xFE0, // BSR  (POR `---- 0000` = 0)
        0xFE2, // FSR1H
        0xFEA, // FSR0H
        // PC / TBLPTR / TABLAT cluster: all zero on both POR
        // and MCLR.  PC bytes are already zeroed by
        // apply_reset's set_pc(0), but the SFR-mapped slots
        // need explicit clearing for non-POR resets that do
        // not run the data-memory wipe.  TBLPTR* / TABLAT
        // are pure SFR storage; if a TBLRD/TBLWT was in
        // flight before the reset, the residual pointer
        // would survive without this.
        0xFF5, // TABLAT
        0xFF6, // TBLPTRL
        0xFF7, // TBLPTRH
        0xFF8, // TBLPTRU
        0xFF9, // PCL
        0xFFA, // PCLATH
        0xFFB, // PCLATU
    ];
    for addr in K20_MCLR_ZERO_SFRS {
        core.memory.write_raw(Address::from_raw(*addr), 0);
    }
}

/// SFRs whose MCLR-column value mixes preserved (`u`) bits
/// with fixed bits.  Each entry is `(addr, target_value,
/// reset_mask)`: bits set in `reset_mask` are forced to
/// `target_value`; bits clear in `reset_mask` are preserved
/// from the pre-reset byte.
///
/// Coverage policy: only SFRs whose MCLR row has at least
/// one *fixed* bit (i.e. not all `u`) belong here.  SFRs
/// whose MCLR row is fully `u` (T3CON, STATUS, the timer
/// data registers, WREG, PRODL/H, ADRES{H,L}, CCPR{1,2}{H,L},
/// SSPBUF, FSR{0,1,2}L, PORTC, LATA-C) are MCLR no-ops --
/// they do not need an entry here.  The BOR path takes care
/// of those via the SFR-window wipe in `apply_reset`'s BOR
/// arm.
fn apply_k20_mclr_rmw_sfrs(core: &mut Core) {
    // (addr, target_value, reset_mask)
    const K20_MCLR_RMW: &[(u16, u8, u8)] = &[
        // INTCON: POR `0000 000x`, MCLR `0000 000u`.  Bits
        // 7..1 reset; bit 0 (RBIF) preserved.
        (0xFF2, 0x00, 0xFE),
        // T1CON: POR `0000 0000`, MCLR `u0uu uuuu`.  Only
        // bit 6 (T1RUN) is fixed-0 on MCLR; the rest are
        // preserved.
        (0xFCD, 0x00, 0x40),
        // EECON1: POR `xx-0 x000`, MCLR `uu-0 u000`.  Bits
        // 5 (-), 4, 2, 1, 0 are fixed-0; bits 7, 6, 3 are
        // preserved on MCLR.  reset_mask = 0b0011_0111 =
        // 0x37 covers the fixed bits.
        (0xFA6, 0x00, 0x37),
        // PORTA: POR `xx0x 0000`, MCLR `uu0u 0000`.  Bits
        // 7, 6, 4 preserved on MCLR; bits 5, 3..0 fixed-0.
        // reset_mask = 0b0010_1111 = 0x2F.
        (0xF80, 0x00, 0x2F),
        // PORTB: POR `xxx0 0000`, MCLR `uuu0 0000`.  Bits
        // 7..5 preserved; bits 4..0 fixed-0.
        (0xF81, 0x00, 0x1F),
        // PORTE: POR `---- x000`, MCLR `---- u000`.  Bit 3
        // (RE3) preserved; bits 2..0 fixed-0; bits 7..4
        // unimplemented.  reset_mask = 0x07.
        (0xF84, 0x00, 0x07),
    ];
    for (addr, target, reset_mask) in K20_MCLR_RMW {
        let old = core.memory.read_raw(Address::from_raw(*addr));
        let new_value = (old & !reset_mask) | (target & reset_mask);
        core.memory.write_raw(Address::from_raw(*addr), new_value);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::memory::Variant;

    fn rcon_byte(core: &Core) -> u8 {
        core.memory.read_raw(Address::from_raw(RCON_ADDR))
    }

    fn fresh_core_and_stack() -> (Core, Stack) {
        (Core::new(Variant::Pic18F2455), Stack::new())
    }

    // ----- POR -----

    #[test]
    fn por_zeros_pc_and_sets_rcon() {
        let (mut core, mut stack) = fresh_core_and_stack();
        core.set_pc(0x4576);
        apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
        assert_eq!(core.pc(), 0);
        // RI=1, TO=1, PD=1, POR=0, BOR=0
        assert_eq!(rcon_byte(&core), RCON_RI | RCON_TO | RCON_PD,);
    }

    #[test]
    fn por_zeroes_data_memory_and_clears_stack() {
        let (mut core, mut stack) = fresh_core_and_stack();
        // Dirty data memory + stack
        core.memory.write_raw(Address::from_raw(0x100), 0x42);
        for _ in 0..5 {
            stack.push(0x1234);
        }
        apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
        // Memory cleared (except RCON which we explicitly set)
        assert_eq!(core.memory.read_raw(Address::from_raw(0x100)), 0);
        // Stack cleared
        assert_eq!(stack.depth(), 0);
        assert!(!stack.overflow());
        assert!(!stack.underflow());
    }

    // ----- BOR -----

    #[test]
    fn bor_sets_rcon_with_por_preserved() {
        let (mut core, mut stack) = fresh_core_and_stack();
        // Pre-BOR RCON has POR=1 (set by software after a prior POR
        // — typical firmware idiom).
        core.memory
            .write_raw(Address::from_raw(RCON_ADDR), RCON_POR);
        apply_reset(&mut core, &mut stack, ResetSource::BrownOut);
        let rcon = rcon_byte(&core);
        // RI=1, TO=1, PD=1, BOR=0; POR preserved.
        assert!(rcon & RCON_RI != 0);
        assert!(rcon & RCON_TO != 0);
        assert!(rcon & RCON_PD != 0);
        assert!(rcon & RCON_BOR == 0);
        assert!(rcon & RCON_POR != 0);
    }

    // ----- MCLR -----

    #[test]
    fn mclr_only_forces_to_high() {
        let (mut core, mut stack) = fresh_core_and_stack();
        // Set RCON to a recognisable pattern: TO=0 (post-WDT) plus
        // some user bits.
        core.memory.write_raw(Address::from_raw(RCON_ADDR), 0x80);
        apply_reset(&mut core, &mut stack, ResetSource::Mclr);
        let rcon = rcon_byte(&core);
        // TO forced to 1; bit 7 (IPEN) preserved.
        assert!(rcon & RCON_TO != 0);
        assert!(rcon & 0x80 != 0);
    }

    /// MCLR/WDT/RESET on a K20 zeros the SFRs whose Tbl 4-4
    /// MCLR column is fully-zero -- not just the non-zero
    /// ones in K20_POR.  Without this, a non-POR reset would
    /// leave dirty PIR1/PIE1/SPBRG/etc. bytes alive.
    #[test]
    fn mclr_zeros_pir1_pie1_spbrg_and_friends_on_k20() {
        let mut core = Core::new(Variant::Pic18F25K20);
        let mut stack = Stack::new();
        // Pre-fill several SFRs with junk a firmware run might
        // leave behind (TXIF set, PIE1 enables, baud divisor).
        for (addr, value) in [
            (0xF9Eu16, 0xFFu8), // PIR1
            (0xF9D, 0x55),      // PIE1
            (0xFA1, 0xAA),      // PIR2
            (0xFA0, 0x33),      // PIE2
            (0xFAD, 0x99),      // TXREG
            (0xFAF, 0x05),      // SPBRG
            (0xF9B, 0x42),      // OSCTUNE
        ] {
            core.memory.write_raw(Address::from_raw(addr), value);
        }
        apply_reset(&mut core, &mut stack, ResetSource::Mclr);
        for addr in [0xF9Eu16, 0xF9D, 0xFA1, 0xFA0, 0xFAD, 0xFAF, 0xF9B] {
            assert_eq!(
                core.memory.read_raw(Address::from_raw(addr)),
                0,
                "SFR 0x{addr:03X} must zero on MCLR per Tbl 4-4"
            );
        }
        // K20_POR's non-zero entries also re-establish.
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xFCB)),
            0xFF,
            "PR2 must be 0xFF after MCLR (K20_POR re-applies)"
        );
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xFAC)),
            0x02,
            "TXSTA must be 0x02 (TRMT=1) after MCLR"
        );
    }

    /// MCLR also zeros TBLPTR / TABLAT / PCL / PCLATH /
    /// PCLATU per Tbl 4-4 (POR=0, MCLR=0 for all seven).
    #[test]
    fn mclr_zeros_tblptr_tablat_and_pc_sfrs_on_k20() {
        let mut core = Core::new(Variant::Pic18F25K20);
        let mut stack = Stack::new();
        for (addr, value) in [
            (0xFF5u16, 0xAA), // TABLAT
            (0xFF6, 0x12),    // TBLPTRL
            (0xFF7, 0x34),    // TBLPTRH
            (0xFF8, 0x05),    // TBLPTRU (only bits 5..0 implemented)
            (0xFF9, 0x42),    // PCL
            (0xFFA, 0x10),    // PCLATH
            (0xFFB, 0x01),    // PCLATU
        ] {
            core.memory.write_raw(Address::from_raw(addr), value);
        }
        apply_reset(&mut core, &mut stack, ResetSource::Mclr);
        for addr in [0xFF5u16, 0xFF6, 0xFF7, 0xFF8, 0xFF9, 0xFFA, 0xFFB] {
            assert_eq!(
                core.memory.read_raw(Address::from_raw(addr)),
                0,
                "SFR 0x{addr:03X} must zero on MCLR"
            );
        }
    }

    /// MCLR's INTCON RMW: bits 7..1 reset to 0; bit 0 (RBIF)
    /// preserved.
    #[test]
    fn mclr_intcon_resets_high_bits_preserves_rbif() {
        let mut core = Core::new(Variant::Pic18F25K20);
        let mut stack = Stack::new();
        // INTCON has GIE/PEIE/TMR0IE/INT0IE/RBIE set + RBIF.
        core.memory.write_raw(Address::from_raw(0xFF2), 0xFF);
        apply_reset(&mut core, &mut stack, ResetSource::Mclr);
        let intcon = core.memory.read_raw(Address::from_raw(0xFF2));
        assert_eq!(
            intcon & 0xFE,
            0,
            "INTCON bits 7..1 must reset on MCLR (got 0x{intcon:02X})"
        );
        assert_eq!(
            intcon & 0x01,
            0x01,
            "INTCON bit 0 (RBIF) must be preserved on MCLR"
        );
    }

    /// BOR shares the POR/BOR column of Tbl 4-4, which has
    /// no `u` (preserved) entries -- only `0`, `1`, `x`, and
    /// `q`.  This codebase treats `x` as 0, so BOR must
    /// fully zero INTCON (including bit 0 RBIF), unlike MCLR
    /// which preserves bit 0 per the `0000 000u` MCLR row.
    /// PIR1 zeroes on BOR (POR/BOR row `0000 0000`).
    #[test]
    fn bor_fully_zeros_pir1_and_intcon_on_k20() {
        let mut core = Core::new(Variant::Pic18F25K20);
        let mut stack = Stack::new();
        core.memory.write_raw(Address::from_raw(0xF9E), 0xFF); // PIR1
        core.memory.write_raw(Address::from_raw(0xFF2), 0xFF); // INTCON
        apply_reset(&mut core, &mut stack, ResetSource::BrownOut);
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xF9E)),
            0,
            "PIR1 must zero on BOR"
        );
        let intcon = core.memory.read_raw(Address::from_raw(0xFF2));
        assert_eq!(
            intcon, 0,
            "INTCON must FULLY zero on BOR (Tbl 4-4 POR/BOR = 0000 000x)"
        );
    }

    /// BOR fully zeros T1CON / T3CON / EECON1 / STATUS / RCSTA
    /// per Tbl 4-4 POR/BOR column (treating `x` as 0).  MCLR
    /// preserves their `u` bits (or is a no-op for fully-`u`
    /// rows), so BOR must NOT inherit MCLR's preservation.
    #[test]
    fn bor_fully_zeros_mixed_mclr_sfrs_on_k20() {
        let mut core = Core::new(Variant::Pic18F25K20);
        let mut stack = Stack::new();
        for (addr, junk) in [
            (0xFA6u16, 0xFFu8), // EECON1
            (0xFAB, 0xFF),      // RCSTA
            (0xFB1, 0xFF),      // T3CON
            (0xFCD, 0xFF),      // T1CON
            (0xFD8, 0xFF),      // STATUS (writes the 5 implemented bits)
        ] {
            core.memory.write_raw(Address::from_raw(addr), junk);
        }
        apply_reset(&mut core, &mut stack, ResetSource::BrownOut);
        for addr in [0xFA6u16, 0xFAB, 0xFB1, 0xFCD, 0xFD8] {
            assert_eq!(
                core.memory.read_raw(Address::from_raw(addr)),
                0,
                "0x{addr:03X} must FULLY zero on BOR"
            );
        }
    }

    /// MCLR's RMW pass for T1CON: only bit 6 (T1RUN) is
    /// reset; bits 7, 5..0 are preserved.
    #[test]
    fn mclr_t1con_resets_bit_6_preserves_rest() {
        let mut core = Core::new(Variant::Pic18F25K20);
        let mut stack = Stack::new();
        // T1CON pre-reset = 1011 1011 = 0xBB.  After MCLR:
        // bit 6 cleared -> 1011 1011 & ~0x40 = 1011 1011 -
        // (no bit 6 was set).  Use 0xFF instead so bit 6 set.
        core.memory.write_raw(Address::from_raw(0xFCD), 0xFF);
        apply_reset(&mut core, &mut stack, ResetSource::Mclr);
        let t1con = core.memory.read_raw(Address::from_raw(0xFCD));
        assert_eq!(
            t1con & 0x40,
            0,
            "T1CON bit 6 (T1RUN) must clear on MCLR (got 0x{t1con:02X})"
        );
        assert_eq!(
            t1con & !0x40,
            0xBF,
            "T1CON bits 7, 5..0 must be preserved (got 0x{t1con:02X})"
        );
    }

    /// MCLR's RMW pass for EECON1: bits 5,4,2,1,0 reset to
    /// 0; bits 7, 6, 3 preserved.  reset_mask = 0x37.
    #[test]
    fn mclr_eecon1_resets_fixed_bits_preserves_u_bits() {
        let mut core = Core::new(Variant::Pic18F25K20);
        let mut stack = Stack::new();
        core.memory.write_raw(Address::from_raw(0xFA6), 0xFF);
        apply_reset(&mut core, &mut stack, ResetSource::Mclr);
        let eecon1 = core.memory.read_raw(Address::from_raw(0xFA6));
        // Bits 7, 6, 3 = 0xC8 should be preserved as 1.
        assert_eq!(eecon1 & 0xC8, 0xC8);
        // Bits 5, 4, 2, 1, 0 = 0x37 should be 0.
        assert_eq!(eecon1 & 0x37, 0);
    }

    /// BOR wipes the entire SFR window 0xF60..0xFFF, so any
    /// SFR firmware previously set survives only via the
    /// K20_POR re-application.  GPRs survive untouched.
    /// Iterates the full window so a regression that skipped
    /// any sub-range still trips.
    #[test]
    fn bor_wipes_full_sfr_window_preserves_gprs() {
        // The K20_POR table from this module enumerates the
        // SFRs that come up at non-zero values after a
        // POR/BOR.  Any address NOT in this list must end at
        // 0 after the BOR wipe.  Build the lookup once.
        let k20_por_addrs: std::collections::HashSet<u16> = [
            0xFF1u16, 0xFF0, 0xFD5, 0xFD3, 0xFD2, 0xFCB, 0xFAC, 0xFB9, 0xFB8, 0xF9F, 0xFA2, 0xF92,
            0xF93, 0xF94, 0xF7E, 0xF7F, 0xF7C, 0xF78, 0xF77,
            // RCON is also expected to be the composed BOR
            // value, not 0 -- exclude it from the "must be 0"
            // assertion.
            0xFD0,
        ]
        .into_iter()
        .collect();

        let mut core = Core::new(Variant::Pic18F25K20);
        let mut stack = Stack::new();

        for addr in 0xF60u16..=0xFFF {
            core.memory.write_raw(Address::from_raw(addr), 0xAB);
        }
        for addr in [0x000u16, 0x080, 0x100, 0xF00, 0xF5F] {
            core.memory.write_raw(Address::from_raw(addr), 0xCD);
        }
        apply_reset(&mut core, &mut stack, ResetSource::BrownOut);

        // Every non-K20_POR SFR must be 0.  Iterate the full
        // window to catch any sub-range the wipe might miss.
        for addr in 0xF60u16..=0xFFF {
            if k20_por_addrs.contains(&addr) {
                continue;
            }
            assert_eq!(
                core.memory.read_raw(Address::from_raw(addr)),
                0,
                "non-K20_POR SFR 0x{addr:03X} must be 0 after BOR wipe"
            );
        }
        // K20_POR non-zero entries are re-established.
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFCB)), 0xFF, "PR2");
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xFD5)),
            0xFF,
            "T0CON"
        );
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xFAC)),
            0x02,
            "TXSTA TRMT"
        );
        // GPRs survive.
        for addr in [0x000u16, 0x080, 0x100, 0xF00, 0xF5F] {
            assert_eq!(
                core.memory.read_raw(Address::from_raw(addr)),
                0xCD,
                "GPR 0x{addr:03X} must survive BOR"
            );
        }
    }

    /// MCLR's RMW pass for the PORT SFRs: PORTA preserves
    /// bits 7/6/4 (RA7/RA6/RA4 `u`); PORTB preserves bits
    /// 7/6/5 (`uuu0 0000`); PORTE preserves bit 3 (RE3 `u`).
    /// Other implemented bits clear to 0.
    #[test]
    fn mclr_porta_portb_porte_rmw_masks() {
        let mut core = Core::new(Variant::Pic18F25K20);
        let mut stack = Stack::new();
        core.memory.write_raw(Address::from_raw(0xF80), 0xFF); // PORTA
        core.memory.write_raw(Address::from_raw(0xF81), 0xFF); // PORTB
        core.memory.write_raw(Address::from_raw(0xF84), 0xFF); // PORTE
        apply_reset(&mut core, &mut stack, ResetSource::Mclr);
        // PORTA: preserve bits 7,6,4 = 0xD0; reset 5,3..0 = 0x2F.
        assert_eq!(core.memory.read_raw(Address::from_raw(0xF80)), 0xD0);
        // PORTB: preserve 7..5 = 0xE0; reset 4..0 = 0x1F.
        assert_eq!(core.memory.read_raw(Address::from_raw(0xF81)), 0xE0);
        // PORTE: preserve bit 3 only = 0x08; reset 2..0 = 0x07.
        // Bits 7..4 are unimplemented -- they came in as 0xF0
        // from the 0xFF poison but reads return 0; the SFR
        // backing byte may still be 0xF8 since memory write
        // doesn't enforce bit-level masking.  Assert only the
        // RMW-affected bits to keep the test focused.
        let porte = core.memory.read_raw(Address::from_raw(0xF84));
        assert_eq!(porte & 0x0F, 0x08, "RE3 preserved, RE2..0 reset");
    }

    /// MCLR is fully `u` (preserved) for STATUS and T3CON
    /// per Tbl 4-4 column-2: `---u uuuu` and `uuuu uuuu`
    /// respectively.  Neither appears in K20_MCLR_ZERO_SFRS
    /// nor K20_MCLR_RMW; BOR's SFR-window wipe handles their
    /// POR/BOR reset.  Test asserts MCLR doesn't disturb
    /// pre-reset values.
    #[test]
    fn mclr_preserves_t3con_status_on_k20() {
        let mut core = Core::new(Variant::Pic18F25K20);
        let mut stack = Stack::new();
        core.memory.write_raw(Address::from_raw(0xFB1), 0x42); // T3CON
        core.memory.write_raw(Address::from_raw(0xFD8), 0x05); // STATUS
        apply_reset(&mut core, &mut stack, ResetSource::Mclr);
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xFB1)),
            0x42,
            "T3CON must be preserved across MCLR"
        );
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xFD8)) & 0x1F,
            0x05,
            "STATUS implemented bits must be preserved across MCLR"
        );
    }

    /// GPRs (data memory below 0xF60) MUST survive MCLR per
    /// Tbl 4-4 -- only POR wipes RAM.  Regression test against
    /// an over-eager MCLR clear.
    #[test]
    fn mclr_preserves_gpr_data_memory() {
        let mut core = Core::new(Variant::Pic18F25K20);
        let mut stack = Stack::new();
        core.memory.write_raw(Address::from_raw(0x100), 0x42);
        core.memory.write_raw(Address::from_raw(0x200), 0xA5);
        apply_reset(&mut core, &mut stack, ResetSource::Mclr);
        assert_eq!(core.memory.read_raw(Address::from_raw(0x100)), 0x42);
        assert_eq!(core.memory.read_raw(Address::from_raw(0x200)), 0xA5);
    }

    #[test]
    fn mclr_zeros_stkptr_but_preserves_flags_and_slot_data() {
        // DS39632E §5.4: "On Reset, the Stack Pointer value
        // will be zero."  Table 4-1: STKFUL=u, STKUNF=u for
        // MCLR.  So depth → 0 but flags + slot data persist.
        let (mut core, mut stack) = fresh_core_and_stack();
        stack.push(0x4576);
        stack.push(0x4FE0);
        apply_reset(&mut core, &mut stack, ResetSource::Mclr);
        assert_eq!(stack.depth(), 0);
        // Slot data preserved — firmware can pull stored bytes
        // back via TOSU/TOSH/TOSL after writing STKPTR.depth.
        stack.write_stkptr(2);
        assert_eq!(stack.depth(), 2);
        assert_eq!(stack.top(), 0x4FE0);
    }

    #[test]
    fn mclr_preserves_underflow_flag() {
        // STKUNF is sticky and per DS39632E Table 4-1
        // (STKUNF=u for MCLR) it survives across an MCLR
        // reset.  Set the flag on the same stack we then
        // reset, then verify it's still asserted.
        let (mut core, mut stack) = fresh_core_and_stack();
        // Pop on empty to latch STKUNF.
        let _ = stack.pop();
        assert!(stack.underflow());
        // Push something on top so depth is non-zero pre-reset
        // (forces the depth-zeroing transition to actually
        // happen; without this depth is already 0 and the test
        // wouldn't exercise the change).
        stack.push(0x1000);
        assert_eq!(stack.depth(), 1);
        apply_reset(&mut core, &mut stack, ResetSource::Mclr);
        assert_eq!(stack.depth(), 0);
        assert!(stack.underflow());
    }

    #[test]
    fn mclr_preserves_overflow_flag() {
        let (mut core, mut stack) = fresh_core_and_stack();
        for i in 0..31 {
            stack.push(0x100 + i as u32);
        }
        // STKFUL latched.
        assert!(stack.overflow());
        apply_reset(&mut core, &mut stack, ResetSource::Mclr);
        // Pointer back to 0; STKFUL still latched.
        assert_eq!(stack.depth(), 0);
        assert!(stack.overflow());
    }

    #[test]
    fn bor_zeros_stkptr_but_preserves_flags_and_slot_data() {
        let (mut core, mut stack) = fresh_core_and_stack();
        stack.push(0x4576);
        stack.push(0x4FE0);
        for _ in 0..31 {
            // Force STKFUL latched so we can confirm survival.
            stack.push(0);
        }
        assert!(stack.overflow());
        apply_reset(&mut core, &mut stack, ResetSource::BrownOut);
        assert_eq!(stack.depth(), 0);
        assert!(stack.overflow());
    }

    #[test]
    fn wdt_zeros_stkptr() {
        let (mut core, mut stack) = fresh_core_and_stack();
        stack.push(0x1000);
        apply_reset(&mut core, &mut stack, ResetSource::Wdt);
        assert_eq!(stack.depth(), 0);
    }

    #[test]
    fn reset_instruction_zeros_stkptr() {
        let (mut core, mut stack) = fresh_core_and_stack();
        stack.push(0x1000);
        stack.push(0x2000);
        apply_reset(&mut core, &mut stack, ResetSource::ResetInstruction);
        assert_eq!(stack.depth(), 0);
    }

    // ----- WDT -----

    #[test]
    fn wdt_clears_to() {
        let (mut core, mut stack) = fresh_core_and_stack();
        core.memory.write_raw(Address::from_raw(RCON_ADDR), 0xFF);
        apply_reset(&mut core, &mut stack, ResetSource::Wdt);
        let rcon = rcon_byte(&core);
        assert_eq!(rcon & RCON_TO, 0);
        // Other bits preserved
        assert_eq!(rcon | RCON_TO, 0xFF);
    }

    // ----- RESET instruction -----

    #[test]
    fn reset_instruction_clears_ri() {
        let (mut core, mut stack) = fresh_core_and_stack();
        core.memory.write_raw(Address::from_raw(RCON_ADDR), 0xFF);
        apply_reset(&mut core, &mut stack, ResetSource::ResetInstruction);
        let rcon = rcon_byte(&core);
        assert_eq!(rcon & RCON_RI, 0);
        // Other bits preserved
        assert_eq!(rcon | RCON_RI, 0xFF);
    }

    // ----- Stack Full / Underflow -----

    /// Stack-fault resets share Tbl 4-4 column 6 SFR-reset
    /// semantics with MCLR/WDT/RESET (codex review of 41d6195
    /// HIGH).  Concretely: after `apply_reset(StackFull)` the
    /// post-reset `peripherals.sync_from_memory` pass runs,
    /// re-derives Timer3's RD16-aware shadow from the now-
    /// canonical SFR memory.  This test pins that the SFR-side
    /// reset machinery executes for stack-fault resets -- it
    /// does NOT make a silicon-fidelity claim about whether
    /// the post-reset Timer3 live counter is "correct" relative
    /// to the silicon's internal hidden register.  The latter
    /// is a Phase-2 concern (peripheral self-reset semantics)
    /// outside the scope of task #16.  Codex review of 5a315b3
    /// LOW noted that the prior wording overclaimed silicon
    /// correctness for the live-shadow value.
    #[test]
    fn stack_full_runs_post_reset_peripheral_sync() {
        let mut core = Core::new(Variant::Pic18F25K20);
        let mut stack = Stack::new();
        // Set up Timer3 in RD16 mode with a divergent
        // live/buffer state: live=0x05, memory[TMR3H]=0x99
        // (a staged firmware buffer write in RD16=1 mode).
        core.memory.write_raw(Address::from_raw(0xFB1), 0x81); // T3CON: TMR3ON|RD16
        core.peripherals
            .timers
            .on_sfr_write(0xFB1, 0x81, &mut core.memory);
        core.peripherals.timers.tick_tcy(0x500, &mut core.memory);
        core.memory.write_raw(Address::from_raw(0xFB3), 0x99); // staged buffer
        core.peripherals
            .timers
            .on_sfr_write(0xFB3, 0x99, &mut core.memory);
        // Pre-reset live-shadow snapshot to detect that
        // sync_from_memory ran (it overwrites the pre-reset
        // value with memory[TMR3H]).
        let pre_live = core.peripherals.timers.tmr3h_live_for_test();
        for i in 0..30 {
            stack.push(0x100 + i as u32);
        }
        stack.push(0x131);
        apply_reset(&mut core, &mut stack, ResetSource::StackFull);
        // T3CON / TMR3H rows are fully `u` (preserved) on
        // Tbl 4-4 column 6 -- the SFR-side reset does not
        // touch them.  `sync_from_memory` then mirrors
        // memory[TMR3H] into tmr3h_live; assert the post-
        // reset live shadow matches the SFR-memory value
        // (tracking the model contract that sync is
        // executed).  Silicon-fidelity of peripheral
        // internal hidden state is deferred.
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xFB3)),
            0x99,
            "TMR3H is fully `u` on Tbl 4-4 col 6 -> preserved across reset"
        );
        let post_live = core.peripherals.timers.tmr3h_live_for_test();
        assert_eq!(
            post_live,
            core.memory.read_raw(Address::from_raw(0xFB3)),
            "post-reset live shadow must equal memory[TMR3H] (model contract)"
        );
        assert_ne!(
            post_live, pre_live,
            "sync_from_memory must run -- post-reset live shadow \
             differs from pre-reset divergent value"
        );
    }

    #[test]
    fn stack_full_reset_zeros_depth_keeps_stkful() {
        let (mut core, mut stack) = fresh_core_and_stack();
        for i in 0..31 {
            stack.push(0x100 + i as u32);
        }
        // STKFUL is now set (the 31st push set it).
        assert!(stack.overflow());
        apply_reset(&mut core, &mut stack, ResetSource::StackFull);
        // Stack depth back to 0 but STKFUL stays asserted (per
        // DS39632E §5.4.2).
        assert_eq!(stack.depth(), 0);
        assert!(stack.overflow());
        assert!(!stack.underflow());
    }

    #[test]
    fn stack_full_reset_does_not_touch_rcon() {
        let (mut core, mut stack) = fresh_core_and_stack();
        core.memory.write_raw(Address::from_raw(RCON_ADDR), 0xA5);
        apply_reset(&mut core, &mut stack, ResetSource::StackFull);
        assert_eq!(rcon_byte(&core), 0xA5);
    }

    /// Both K20 and 2455 must clear INTCON bits 7..1 on
    /// stack-fault reset (codex review of 5a315b3 MEDIUM:
    /// the prior K20-only path left 2455's INTCON.GIE
    /// set, which would let a still-pending IRQ
    /// immediately re-vector after reset).  RBIF (bit 0)
    /// is preserved per Tbl 4-4 column 6.
    #[test]
    fn stack_full_clears_intcon_on_both_variants() {
        for variant in [Variant::Pic18F25K20, Variant::Pic18F2455] {
            let mut core = Core::new(variant);
            let mut stack = Stack::new();
            // Set every INTCON bit.
            core.memory.write_raw(Address::from_raw(0xFF2), 0xFF);
            apply_reset(&mut core, &mut stack, ResetSource::StackFull);
            let intcon = core.memory.read_raw(Address::from_raw(0xFF2));
            assert_eq!(
                intcon & 0xFE,
                0,
                "{:?}: INTCON bits 7..1 must clear on stack-full reset",
                variant
            );
            assert_eq!(
                intcon & 0x01,
                0x01,
                "{:?}: INTCON.RBIF (bit 0) preserved per Tbl 4-4 col 6",
                variant
            );
        }
    }

    /// Task #30 root-cause: V3.1 MAIN's boot path calls
    /// `wait_trmt_bounded` which polls TXSTA.TRMT.  TRMT's
    /// POR value is 1 per DS39632E Tbl 4-4, but our 2455
    /// POR formerly wiped the SFR window to 0 with no
    /// re-seeding (only K20 had a POR table).  Result:
    /// firmware times out, hits `hard_reset`, reboots in
    /// an infinite loop, never reaches the chain protocol
    /// parser.  This test pins the 2455 POR contract for
    /// every IRQ + UART SFR the boot path depends on.
    #[test]
    fn por_seeds_2455_irq_and_uart_sfrs_per_tbl_4_4() {
        let mut core = Core::new(Variant::Pic18F2455);
        let mut stack = Stack::new();
        apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
        // The most important one for task #30: TRMT=1
        // (TXSTA bit 1) so MAIN's wait_trmt_bounded poll
        // succeeds at boot.
        let txsta = core.memory.read_raw(Address::from_raw(0xFAC));
        assert_eq!(
            txsta & 0x02,
            0x02,
            "TXSTA.TRMT must be 1 at POR (DS Tbl 4-4 `0000 0010`)"
        );
        // INTCON2 / INTCON3: per-bit non-zero defaults so
        // firmware reads RBPU=1 / TMR0IP=1 etc.
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xFF1)),
            0xF5,
            "INTCON2 = 0xF5 (RBPU/INTEDG0/1/2/TMR0IP/RBIP=1)"
        );
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xFF0)),
            0xC0,
            "INTCON3 = 0xC0 (INT1IP/INT2IP=1)"
        );
        // T0CON / PR2 / BAUDCON / IPRn: all non-zero
        // POR defaults per Tbl 4-4.
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xFD5)),
            0xFF,
            "T0CON = 0xFF (timer disabled, max prescaler)"
        );
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xFCB)),
            0xFF,
            "PR2 = 0xFF (address 0xFCB per DS Tbl 5-1)"
        );
        // RCSTA at 0xFAB stays zero (POR value `0000 000x`,
        // SFR-window wipe leaves it 0; the prior commit's
        // typo wrote 0xFF here, which would have set
        // SPEN/CREN/FERR/OERR pre-firmware).
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xFAB)),
            0,
            "RCSTA = 0 at POR (regression guard for the
             swapped PR2/RCSTA address typo)"
        );
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xFB8)),
            0x40,
            "BAUDCON = 0x40 (RCIDL=1)"
        );
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xF9F)),
            0x7F,
            "IPR1 = 0x7F (28-pin SPPIP unimplemented)"
        );
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xFA2)),
            0xFF,
            "IPR2 = 0xFF"
        );
    }

    /// FID-07: K20 reset q-rows must be CONFIG-derived, not
    /// gpsim-pinned.  DS40001303H Table 5-2 note 5 gates RA6/RA7
    /// PORTA availability on oscillator mode; note 6 gates ANSELH
    /// on PBADEN.
    #[test]
    fn k20_por_resolves_trisa_and_anselh_from_config() {
        let mut core = Core::new(Variant::Pic18F25K20);
        let mut cfg = [0u8; 14];
        cfg[1] = 0x01; // FOSC=XT: RA6/RA7 are oscillator pins.
        cfg[5] = 0x00; // PBADEN=0.
        core.config = Config::from_bytes(cfg);
        let mut stack = Stack::new();
        apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xF92)), 0x3F);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xF7F)), 0x00);

        let mut ec_core = Core::new(Variant::Pic18F25K20);
        cfg[1] = 0x04; // FOSC=ECIO: RA6 is a PORTA pin.
        cfg[5] = 0x02; // PBADEN=1.
        ec_core.config = Config::from_bytes(cfg);
        apply_reset(&mut ec_core, &mut Stack::new(), ResetSource::PowerOn);
        assert_eq!(ec_core.memory.read_raw(Address::from_raw(0xF92)), 0x7F);
        assert_eq!(ec_core.memory.read_raw(Address::from_raw(0xF7F)), 0x1F);
    }

    /// FID-07: 2455 POR/BOR now covers the OSCCON/TRIS/USB rows
    /// that were previously left at zero.  DS39632E Table 4-4
    /// gives OSCCON=0100 q000, TRISC=11-- -111, UEPx/UCFG/UCON
    /// reset-zero; Table 5-2 note 5 makes TRISA<6> depend on
    /// CONFIG1H.FOSC.
    #[test]
    fn pic2455_por_seeds_osc_tris_and_usb_sfr_rows() {
        let mut core = Core::new(Variant::Pic18F2455);
        core.config = Config::from_bytes([
            0x3A, 0x46, 0x3E, 0x1E, 0xFF, 0x00, 0x80, 0xFF, 0x0F, 0xC0, 0x0F, 0xA0, 0x0F, 0x40,
        ]);
        let mut stack = Stack::new();
        apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFD3)), 0x40);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFD2)), 0x05);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xF92)), 0x7F);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xF94)), 0xC7);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFB4)), 0x07);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xF70)), 0x00); // UEP0
        assert_eq!(core.memory.read_raw(Address::from_raw(0xF7F)), 0x00); // UEP15
        assert_eq!(core.memory.read_raw(Address::from_raw(0xF6F)), 0x00); // UCFG
        assert_eq!(core.memory.read_raw(Address::from_raw(0xF6D)), 0x00); // UCON
        assert_eq!(core.memory.read_raw(Address::from_raw(0xF68)), 0x00); // UIR
    }

    /// FID-07: 2455 MCLR/WDT/RESET/stack resets use their own
    /// DS39632E table, not the K20 table and not a preserve-all
    /// shortcut.  This representative WDT reset checks fixed,
    /// RMW-preserved, and USB-reset rows in one pass.
    #[test]
    fn pic2455_non_por_reset_uses_variant_table() {
        let mut core = Core::new(Variant::Pic18F2455);
        let mut stack = Stack::new();
        for addr in [0xF70, 0xF7F, 0xF6F, 0xF6D, 0xF68, 0xFD3, 0xF94] {
            core.memory.write_raw(Address::from_raw(addr), 0xAA);
        }
        core.memory.write_raw(Address::from_raw(0xFF2), 0xFF); // INTCON, RBIF preserved.
        core.memory.write_raw(Address::from_raw(0xF80), 0xFF); // PORTA preserves RA6/RA4.
        apply_reset(&mut core, &mut stack, ResetSource::Wdt);

        assert_eq!(core.memory.read_raw(Address::from_raw(0xF70)), 0x00);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xF7F)), 0x00);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xF6F)), 0x00);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xF6D)), 0x00);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xF68)), 0x00);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFD3)), 0x40);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xF94)), 0xC7);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFF2)), 0x01);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xF80)), 0x50);
    }

    #[test]
    fn stack_underflow_clears_intcon_on_both_variants() {
        for variant in [Variant::Pic18F25K20, Variant::Pic18F2455] {
            let mut core = Core::new(variant);
            let mut stack = Stack::new();
            core.memory.write_raw(Address::from_raw(0xFF2), 0xFF);
            apply_reset(&mut core, &mut stack, ResetSource::StackUnderflow);
            let intcon = core.memory.read_raw(Address::from_raw(0xFF2));
            assert_eq!(intcon & 0xFE, 0, "{:?}: INTCON bits 7..1 clear", variant);
            assert_eq!(intcon & 0x01, 0x01, "{:?}: RBIF preserved", variant);
        }
    }

    /// Task #31: 2455 stack-fault reset broadens the SFR
    /// clear beyond INTCON to cover the full IRQ-related
    /// Tbl 4-4 column-6 group: PIE1 / PIR1 / PIE2 / PIR2
    /// zero, INTCON2 = 0xF5, INTCON3 = 0xC0, IPR1 = 0x7F
    /// (SPPIP bit 7 unimplemented on 28-pin 2455 per DS
    /// footnote 3), IPR2 = 0xFF, WDTCON zero.  Without these
    /// clears, a stack-
    /// fault reset would leave stale enable / flag bits
    /// that could re-trigger an IRQ on the very next
    /// `step()` after the reset, even with INTCON.GIE
    /// cleared (because re-enabling GIE in firmware would
    /// re-vector on the stale flag).  Codex review of
    /// 95722c8 HIGH: addresses corrected to the DS39632E
    /// Tbl 5-1 layout (0xF9D-0xFA2 / 0xFD1) -- the prior
    /// commit used wrong addresses (0xF7D-0xF82 / 0xFB1)
    /// that hit USB / port / T3CON registers instead.
    #[test]
    fn stack_full_reset_2455_broader_irq_sfrs() {
        let mut core = Core::new(Variant::Pic18F2455);
        let mut stack = Stack::new();
        // Pre-load every IRQ-related SFR with a non-zero
        // sentinel so the reset can transition each.
        for addr in [
            0xF9D, // PIE1
            0xF9E, // PIR1
            0xF9F, // IPR1
            0xFA0, // PIE2
            0xFA1, // PIR2
            0xFA2, // IPR2
            0xFD1, // WDTCON
            0xFF0, // INTCON3
            0xFF1, // INTCON2
            0xFF2, // INTCON
        ] {
            core.memory.write_raw(Address::from_raw(addr), 0xAA);
        }
        apply_reset(&mut core, &mut stack, ResetSource::StackFull);
        // Zeroed:
        for (name, addr) in [
            ("PIE1", 0xF9D),
            ("PIR1", 0xF9E),
            ("PIE2", 0xFA0),
            ("PIR2", 0xFA1),
            ("WDTCON", 0xFD1),
        ] {
            assert_eq!(
                core.memory.read_raw(Address::from_raw(addr)),
                0,
                "{} must zero on 2455 stack-fault reset",
                name
            );
        }
        // Fixed non-zero:
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xFF1)),
            0xF5,
            "INTCON2 = 0xF5 (RBPU/INTEDGn/TMR0IP/RBIP=1, unimpl=0)"
        );
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xFF0)),
            0xC0,
            "INTCON3 = 0xC0 (INT1IP/INT2IP=1, others 0)"
        );
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xF9F)),
            0x7F,
            "IPR1 = 0x7F on 28-pin 2455 (SPPIP bit 7 unimplemented)"
        );
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xFA2)),
            0xFF,
            "IPR2 = 0xFF"
        );
        // INTCON RMW (bits 7..1 clear, RBIF preserved).
        // Pre-load was 0xAA = 1010_1010, so RBIF (bit 0) was
        // 0; post-reset bits 7..1 clear so the byte is 0.
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0xFF2)) & 0xFE,
            0,
            "INTCON bits 7..1 clear"
        );
    }

    /// Task #31 followup: same broader SFR clears on
    /// StackUnderflow path.
    #[test]
    fn stack_underflow_reset_2455_broader_irq_sfrs() {
        let mut core = Core::new(Variant::Pic18F2455);
        let mut stack = Stack::new();
        for addr in [0xF9D, 0xF9E, 0xFA0, 0xFA1, 0xFD1] {
            core.memory.write_raw(Address::from_raw(addr), 0xAA);
        }
        apply_reset(&mut core, &mut stack, ResetSource::StackUnderflow);
        for (name, addr) in [
            ("PIE1", 0xF9D),
            ("PIR1", 0xF9E),
            ("PIE2", 0xFA0),
            ("PIR2", 0xFA1),
            ("WDTCON", 0xFD1),
        ] {
            assert_eq!(
                core.memory.read_raw(Address::from_raw(addr)),
                0,
                "{} must zero on 2455 stack-underflow reset",
                name
            );
        }
    }

    #[test]
    fn stack_underflow_reset_latches_stkunf() {
        let (mut core, mut stack) = fresh_core_and_stack();
        // Pop on empty to set STKUNF.
        let _ = stack.pop();
        assert!(stack.underflow());
        apply_reset(&mut core, &mut stack, ResetSource::StackUnderflow);
        assert_eq!(stack.depth(), 0);
        assert!(stack.underflow());
    }

    #[test]
    fn stack_underflow_reset_does_not_touch_rcon() {
        let (mut core, mut stack) = fresh_core_and_stack();
        core.memory.write_raw(Address::from_raw(RCON_ADDR), 0x33);
        apply_reset(&mut core, &mut stack, ResetSource::StackUnderflow);
        assert_eq!(rcon_byte(&core), 0x33);
    }

    // ----- Every reset source returns PC to 0 -----

    #[test]
    fn every_reset_source_returns_pc_to_zero() {
        let sources = [
            ResetSource::PowerOn,
            ResetSource::BrownOut,
            ResetSource::Mclr,
            ResetSource::Wdt,
            ResetSource::ResetInstruction,
            ResetSource::StackFull,
            ResetSource::StackUnderflow,
        ];
        for src in sources {
            let (mut core, mut stack) = fresh_core_and_stack();
            core.set_pc(0x1234);
            apply_reset(&mut core, &mut stack, src);
            assert_eq!(core.pc(), 0, "PC should be 0 after {src:?}");
        }
    }
}
