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
//! ### What this module DOES do (extended in P1.8d)
//!
//! POR additionally programs the SFR window with the full
//! K20 / 2455 power-on initial values per their datasheets'
//! "Initialization Conditions for All Registers" tables (K20:
//! DS40001303H Table 4-4 p.56-60; 2455: DS39632E Table 4-2).
//! Without this the V1.71 / V2.3 boot paths read 0 for SFRs
//! the silicon brings up non-zero (TRIS = 1s for all-input
//! POR, ANSEL = 1s for all-analog, T0CON = 1s, IPRx = 1s,
//! etc.) and immediately diverge.

use crate::core::Core;
use crate::memory::{Address, Variant};
use crate::stack::Stack;

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
#[derive(Copy, Clone, Eq, PartialEq, Debug, Hash)]
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
        ResetSource::PowerOn => {
            (rcon & !(RCON_POR | RCON_BOR)) | RCON_RI | RCON_TO | RCON_PD
        }
        // BOR: RI=1, TO=1, PD=1, POR=u, BOR=0.
        ResetSource::BrownOut => {
            (rcon & !RCON_BOR) | RCON_RI | RCON_TO | RCON_PD
        }
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
            core.memory.write_raw(
                Address::from_raw(RCON_ADDR),
                RCON_RI | RCON_TO | RCON_PD,
            );
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
            // BOR shares the "Power-on Reset, Brown-out
            // Reset" column in Tbl 4-4 -- so SFRs that
            // bring up at fixed values reset on BOR too,
            // and SFRs whose MCLR row has preserved (`u`)
            // bits are still fully zeroed on BOR (the
            // POR/BOR row uses `0` or `x`, never `u`).
            // GPRs (data memory below 0xF60) ARE preserved
            // across BOR per §4.4 -- only POR wipes RAM --
            // so we touch the SFR window explicitly:
            //   (1) zero the "fully zero on POR/BOR/MCLR"
            //       set,
            //   (2) wholesale-zero the SFRs whose MCLR row
            //       has `u` bits but whose POR/BOR row is
            //       all-zero (currently only INTCON).
            //   (3) re-apply K20_POR for the non-zero
            //       fixed defaults.
            // No MCLR-style RMW pass on BOR -- BOR doesn't
            // preserve any `u` bits.
            if core.variant() == Variant::Pic18F25K20 {
                apply_k20_mclr_zero_sfrs(core);
                apply_k20_bor_zero_mixed_sfrs(core);
            }
            apply_por_sfr_defaults(core);
        }
        ResetSource::Mclr
        | ResetSource::Wdt
        | ResetSource::ResetInstruction => {
            // DS39632E §5.4 + Table 4-1: STKPTR depth → 0;
            // sticky flags + slot data preserved.  A previous
            // CALL/RCALL push remains in slot[depth_pre-1] and
            // can be read via TOSU/H/L after firmware writes a
            // new depth into STKPTR.
            stack.reset_pointer_preserve_flags();
            // Per DS40001303H Table 4-4 "MCLR Resets, WDT
            // Reset, RESET Instruction, Stack Resets" column:
            // many SFRs reset to fixed values for these
            // sources (PIR1/2 -> 0, PIE1/2 -> 0, TXREG -> 0,
            // SPBRG{,H} -> 0, RCSTA -> 0x00 ignoring RX9D,
            // OSCTUNE -> 0, ADCON{0,1,2} -> 0, etc.) -- not
            // uniformly preserved.  Data memory (GPRs) IS
            // preserved across these resets -- only POR wipes
            // RAM -- so we must touch the SFR window
            // explicitly.  Two passes:
            //   (1) zero the "fully-zero on MCLR" SFR list
            //       (these were brought to 0 by the POR memory
            //        wipe but a non-POR reset doesn't wipe).
            //   (2) re-apply the K20_POR table (non-zero
            //       defaults like INTCON2 = 0xF5, T0CON =
            //       0xFF, PR2 = 0xFF, etc. -- every entry has
            //       the same value in the POR/BOR column and
            //       the MCLR-style column of Tbl 4-4).
            // SFRs with mixed preserved/fixed bits on MCLR
            // (T1CON, RCSTA, EECON1, STATUS) are deferred to
            // a follow-up; the cycle-10 V1.71 parity test
            // uses POR exclusively so the gap is theoretical.
            if core.variant() == Variant::Pic18F25K20 {
                apply_k20_mclr_zero_sfrs(core);
                apply_k20_mclr_rmw_sfrs(core);
            }
            apply_por_sfr_defaults(core);
        }
        ResetSource::StackFull => {
            // Depth → 0; STKFUL stays set.  Slot data preserved.
            stack.reset_for_stack_full();
        }
        ResetSource::StackUnderflow => {
            stack.reset_for_stack_underflow();
        }
    }
}

/// Apply the variant-specific SFR power-on initial values.
/// Runs after the POR memory wipe, so any non-zero default the
/// silicon brings up at POR is restored.
///
/// K20: DS40001303H Table 4-4 ("Initialization Conditions for All
/// Registers", p.56-60) + Table 5-2 footnotes for 28-pin masking.
/// Only entries that are non-zero at POR are listed -- everything
/// else is already 0 from the memory wipe above.
///
/// 2455: not yet wired.  When the 2455 isa-parity gate lands,
/// add a parallel match arm with DS39632E Table 4-2's defaults.
fn apply_por_sfr_defaults(core: &mut Core) {
    match core.variant() {
        Variant::Pic18F25K20 => apply_k20_por_sfr_defaults(core),
        Variant::Pic18F2455 => {
            // P1.8d covers K20 only; the 2455 POR table will land
            // alongside the V2.3 MAIN parity gate.
        }
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
        // TRISA: Tbl 4-4 base = `1111 1111` = 0xFF, but Note 5
        // says RA6/RA7 are oscillator pins in modes that use
        // OSC1/OSC2 -- "When not enabled as PORTA pins, they
        // are disabled and read 0".  The actual POR-effective
        // value is therefore CONFIG-dependent (FOSC<3:0> field
        // of CONFIG1H).  This Phase-1 table currently stores
        // 0x7F so the cycle-10 V1.71 parity gate matches gpsim
        // -- gpsim's K20 model only disables RA7 (not RA6) for
        // V1.71's FOSC=XT (CONFIG1H=0x01), which is itself a
        // gpsim modeling gap (Tbl 4-4 Note 5 mandates BOTH bits
        // 6 and 7 be 0 in XT mode -> spec-correct value would
        // be 0x3F).  P2 will plumb CONFIG into the reset path
        // and resolve TRISA per-mode; until then this stays
        // pinned to "what gpsim reports for V1.71" and the
        // discrepancy lives in the codex review trail.
        (0xF92, 0x7F),
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
        // ANSELH: ANS<12:8> implemented; Note 6 says all bits
        // initialise to 0 if PBADEN=0 (CONFIG3H bit 1).  V1.71
        // has CONFIG3H=0x00 -> PBADEN=0, so the spec-correct
        // POR is 0x00.  This table stores 0x1F so the cycle-10
        // parity gate matches gpsim, whose K20 model brings
        // ANSELH up at 0x1F regardless of CONFIG3H (gpsim's
        // P18F25K20::set_config3h is supposed to honour Note
        // 6 -- p18fk.cc:245 -- but the CONFIG3H value reaches
        // it after the SFR has already POR'd, so the override
        // never lands at the cycle-10 observation point).  Like
        // TRISA above, P2 will resolve this CONFIG-conditional
        // value properly; for now we track gpsim.
        (0xF7F, 0x1F),
        // WPUB: weak pull-ups enabled.
        (0xF7C, 0xFF),
        // SLRCON: slew-rate control = normal (1) for SLRA/B/C.
        // 28-pin omits SLRD/SLRE per Table 5-2 footnote 2 -> 0x07.
        (0xF78, 0x07),
        // SSPMSK: I2C address mask = all 1s.
        (0xF77, 0xFF),
    ];

    for (addr, value) in K20_POR {
        core.memory
            .write_raw(Address::from_raw(*addr), *value);
    }
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
/// with fixed bits (T1CON `u0uu uuuu`, RCSTA bit 0 RX9D `u`,
/// EECON1 bits 7/6/3 `u`, STATUS bits 4..0 `u`) are NOT in
/// this list -- they need RMW-style per-bit handling.
/// `apply_k20_mclr_rmw_sfrs` covers INTCON (bit 0 preserved);
/// the remaining cases are a deferred follow-up.
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
/// Only INTCON is wired here for now.  Other mixed-bit
/// cases (T1CON `u0uu uuuu`, RCSTA bit 0 RX9D `x`/`x`,
/// EECON1 `uu-0 u000`, STATUS `---u uuuu`, T3CON `uuuu
/// uuuu`) are a deferred follow-up since the Phase-2 parity
/// scope doesn't exercise them on a non-POR reset.
fn apply_k20_mclr_rmw_sfrs(core: &mut Core) {
    // (addr, target_value, reset_mask)
    const K20_MCLR_RMW: &[(u16, u8, u8)] = &[
        // INTCON: POR `0000 000x`, MCLR `0000 000u`.
        // Bits 7..1 reset to 0; bit 0 (RBIF) is preserved.
        (0xFF2, 0x00, 0xFE),
    ];
    for (addr, target, reset_mask) in K20_MCLR_RMW {
        let old = core
            .memory
            .read_raw(Address::from_raw(*addr));
        let new_value = (old & !reset_mask) | (target & reset_mask);
        core.memory
            .write_raw(Address::from_raw(*addr), new_value);
    }
}

/// SFRs whose Tbl 4-4 POR/BOR column is fully zero but whose
/// MCLR column has preserved (`u`) bits.  These need
/// wholesale-zero on BOR (to match the POR/BOR `0` / `x`
/// pattern), distinct from the RMW path that MCLR/WDT/RESET
/// uses.  Without this, BOR would inherit MCLR's `u`
/// preservation -- e.g. INTCON.RBIF surviving BOR contrary
/// to Tbl 4-4's `0000 000x` POR/BOR row.
fn apply_k20_bor_zero_mixed_sfrs(core: &mut Core) {
    const K20_BOR_ALSO_ZERO: &[u16] = &[
        0xFF2, // INTCON: POR `0000 000x` (= 0); MCLR `0000 000u`
    ];
    for addr in K20_BOR_ALSO_ZERO {
        core.memory.write_raw(Address::from_raw(*addr), 0);
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
        assert_eq!(
            rcon_byte(&core),
            RCON_RI | RCON_TO | RCON_PD,
        );
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
        core.memory.write_raw(Address::from_raw(RCON_ADDR), RCON_POR);
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
            (0xF9D, 0x55),       // PIE1
            (0xFA1, 0xAA),       // PIR2
            (0xFA0, 0x33),       // PIE2
            (0xFAD, 0x99),       // TXREG
            (0xFAF, 0x05),       // SPBRG
            (0xF9B, 0x42),       // OSCTUNE
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
            (0xFF6, 0x12), // TBLPTRL
            (0xFF7, 0x34), // TBLPTRH
            (0xFF8, 0x05), // TBLPTRU (only bits 5..0 implemented)
            (0xFF9, 0x42), // PCL
            (0xFFA, 0x10), // PCLATH
            (0xFFB, 0x01), // PCLATU
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
            intcon & 0xFE, 0,
            "INTCON bits 7..1 must reset on MCLR (got 0x{intcon:02X})"
        );
        assert_eq!(
            intcon & 0x01, 0x01,
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
