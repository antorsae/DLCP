//! Cycle-accurate PIC18 instruction executor.
//!
//! Drives [`crate::core::Core`] forward one instruction at a time
//! by:
//!
//!   1. Fetching the 16-bit word at `Core::pc()` from the flash
//!      buffer (and the next word too — required by the decoder
//!      for the four 2-word ops `CALL`, `GOTO`, `MOVFF`, `LFSR`).
//!   2. Decoding via [`crate::isa::decode`].
//!   3. Advancing the PC by the decoded byte count (2 or 4).
//!   4. Dispatching over [`crate::isa::Instruction`] and applying
//!      the instruction's RAM / SFR / stack / cycle-counter side
//!      effects.
//!   5. Returning the Tcy cost (1 / 2 / 3) to the caller, which
//!      P3's chain scheduler converts into the universal-tick
//!      domain.
//!
//! ## Coverage roll-out
//!
//! P1.8b lands the executor incrementally — one or two
//! instruction categories per commit so the per-commit codex
//! review can audit each transition (STATUS-flag fidelity,
//! Access-Bank routing, FSR indirect addressing, etc.) without
//! drowning.  Until the full 75-instruction set is wired,
//! unimplemented variants surface as
//! [`ExecError::Unimplemented`]; the dispatch's wildcard arm
//! shrinks with each commit and disappears entirely once every
//! variant is covered.
//!
//! Reference: DS39632E §26 (PIC18F2455 Instruction Set Summary,
//! Table 26-2) and DS41303G §25 (PIC18F25K20 instruction set —
//! byte-for-byte identical for every opcode this firmware uses).

#![allow(dead_code, reason = "P1.8b executor; consumed by P1.8c/d/e parity tests")]

use crate::core::Core;
use crate::isa::fsr::{FsrAccessMode, classify_fsr_indirect, fsr_high_addr, fsr_low_addr};
use crate::isa::{Access, Dest, FsrIndex, Instruction, decode};
use crate::memory::Address;
use crate::stack::Stack;

// ---- Key SFR addresses consulted by the executor ----------------
//
// Every PIC18 SFR is exposed as a byte in the data-memory map at
// `0xF60..=0xFFF`; the executor uses [`Memory::read_raw`] /
// [`Memory::write_raw`] to access them.  FSR indirect addressing
// (INDFn / POSTINCn / POSTDECn / PREINCn / PLUSWn) IS modelled
// (see `resolve_target_no_commit` below).  PCL writes triggering
// a PC update are still deferred to a future P1.8b sub-commit;
// the helpers here treat PCL as a normal SFR byte for now.

/// `WREG` at 0xFE8.  PIC18's W is exposed as this SFR; reads /
/// writes via the f-operand route through the same byte.
const WREG_ADDR: u16 = 0xFE8;

/// `BSR` at 0xFE0.  Bits 3..0 select the active bank for `a=1`
/// operands; bits 7..4 are unimplemented (read as 0).
const BSR_ADDR: u16 = 0xFE0;

/// `STATUS` at 0xFD8.
const STATUS_ADDR: u16 = 0xFD8;
const STATUS_C: u8 = 0x01;
const STATUS_DC: u8 = 0x02;
const STATUS_Z: u8 = 0x04;
const STATUS_OV: u8 = 0x08;
const STATUS_N: u8 = 0x10;
/// `STATUS` valid bits (bits 5..7 are unimplemented, read as 0).
const STATUS_VALID_MASK: u8 = 0x1F;

/// `PRODL` / `PRODH` -- 8x8 hardware multiplier output
/// (DS39632E §7).  All 8 bits implemented in both bytes; no
/// mask needed.
const PRODL_ADDR: u16 = 0xFF3;
const PRODH_ADDR: u16 = 0xFF4;

// ---- Read/write helpers -----------------------------------------

fn read_w(core: &Core) -> u8 {
    core.memory.read_raw(Address::from_raw(WREG_ADDR))
}

fn write_w(core: &mut Core, value: u8) {
    core.memory.write_raw(Address::from_raw(WREG_ADDR), value);
}

fn read_bsr(core: &Core) -> u8 {
    core.memory.read_raw(Address::from_raw(BSR_ADDR))
}

fn write_bsr(core: &mut Core, value: u8) {
    // Per DS39632E Register 5-2, BSR bits 7..4 are unimplemented.
    core.memory
        .write_raw(Address::from_raw(BSR_ADDR), value & 0x0F);
}

fn read_status(core: &Core) -> u8 {
    core.memory.read_raw(Address::from_raw(STATUS_ADDR))
}

/// Set or clear `mask` bits in STATUS based on `predicate`.  Used
/// by every instruction that touches Z / N / C / DC / OV.
fn set_status_bits(core: &mut Core, mask: u8, predicate: bool) {
    let s = core.memory.read_raw(Address::from_raw(STATUS_ADDR));
    let new = if predicate { s | mask } else { s & !mask };
    core.memory
        .write_raw(Address::from_raw(STATUS_ADDR), new & STATUS_VALID_MASK);
}

/// Set Z and N based on the byte the instruction just produced.
/// Most byte-oriented ops update these two flags; the C/DC/OV
/// updates are op-specific.
fn set_status_zn(core: &mut Core, value: u8) {
    set_status_bits(core, STATUS_Z, value == 0);
    set_status_bits(core, STATUS_N, value & 0x80 != 0);
}

/// Set the full arithmetic-flag set (C, DC, Z, OV, N) after a
/// byte-oriented arithmetic instruction.  The caller computes
/// the result + the C/DC/OV bits via [`add_byte`] / [`sub_byte`]
/// or equivalent; this just commits them to STATUS.
fn set_status_arith(core: &mut Core, result: u8, c: bool, dc: bool, ov: bool) {
    set_status_bits(core, STATUS_C, c);
    set_status_bits(core, STATUS_DC, dc);
    set_status_bits(core, STATUS_OV, ov);
    set_status_zn(core, result);
}

/// Add `a + b + carry_in` and return `(result, C, DC, OV)`.
///
/// * **C**: unsigned overflow (`result_full > 0xFF`).
/// * **DC**: nibble carry (carry from bit 3 to bit 4).
/// * **OV**: signed overflow (both inputs same sign, result
///   different sign).
fn add_byte(a: u8, b: u8, carry_in: bool) -> (u8, bool, bool, bool) {
    let cin = carry_in as u16;
    let result_full = a as u16 + b as u16 + cin;
    let result = result_full as u8;
    let c = result_full > 0xFF;
    let dc = (a & 0x0F) as u16 + (b & 0x0F) as u16 + cin > 0x0F;
    let same_sign_inputs = (a ^ b) & 0x80 == 0;
    let result_diff_sign = (a ^ result) & 0x80 != 0;
    let ov = same_sign_inputs && result_diff_sign;
    (result, c, dc, ov)
}

/// Dispatch helper for byte-oriented arithmetic with a `d`
/// operand (ADDWF, ADDWFC, SUBWF, SUBWFB, SUBFWB, INCF, DECF).
/// Resolves the f-operand once, reads f, calls `compute(f)` for
/// the op-specific arithmetic, sets the full STATUS arithmetic
/// flag set, writes the result to W or back to f per `d`
/// (preserving the §5.3.6 STATUS-skip), then commits any pending
/// FSR mutation -- exactly once per instruction.
fn execute_arith_with_dest<F>(
    core: &mut Core,
    d: Dest,
    a: Access,
    f: u8,
    compute: F,
) where
    F: FnOnce(u8) -> (u8, bool, bool, bool),
{
    execute_op_with_dest(core, d, a, f, |core, fv| {
        let (result, c, dc, ov) = compute(fv);
        set_status_arith(core, result, c, dc, ov);
        result
    });
}

/// Dispatch helper for byte-oriented logical ops with a `d`
/// operand that affect only Z and N (ANDWF, IORWF, XORWF, COMF,
/// RLNCF, RRNCF).  Same resolve / RMW-once / STATUS-skip / FSR
/// commit contract as `execute_arith_with_dest`, but uses
/// `set_status_zn` instead of the full arith-flag set so C, DC,
/// OV survive untouched.
fn execute_logical_with_dest<F>(
    core: &mut Core,
    d: Dest,
    a: Access,
    f: u8,
    compute: F,
) where
    F: FnOnce(u8) -> u8,
{
    execute_op_with_dest(core, d, a, f, |core, fv| {
        let result = compute(fv);
        set_status_zn(core, result);
        result
    });
}

/// Lower-level dispatch helper used by every byte-oriented
/// dispatch arm with a `d` operand.  The `compute_and_status`
/// closure receives `&mut Core` (so it can update STATUS or
/// read other SFRs as part of the op-specific math) plus the
/// byte read from f, and returns the byte to write back.
/// Resolves the f-operand once, reads f, runs the closure,
/// writes to W or f per `d` (preserving the §5.3.6 STATUS-
/// skip), then commits any pending FSR mutation exactly once
/// per instruction (the RMW / once-per-instruction contract
/// established earlier in P1.8b for MOVF d=F).
fn execute_op_with_dest<F>(
    core: &mut Core,
    d: Dest,
    a: Access,
    f: u8,
    compute_and_status: F,
) where
    F: FnOnce(&mut Core, u8) -> u8,
{
    let operand_addr = resolve_f(core, f, a);
    let (target, pending) = resolve_target_no_commit(core, operand_addr);
    let f_value = core.memory.read_raw(target);
    let result = compute_and_status(core, f_value);
    match d {
        Dest::W => write_w(core, result),
        Dest::F => {
            if target.as_u16() != STATUS_ADDR {
                core.memory
                    .write_raw(target, result & sfr_write_mask(target.as_u16()));
            }
        }
    }
    if let Some((fsr, new_fsr)) = pending {
        commit_fsr(core, fsr, new_fsr);
    }
}

/// Compute `minuend - subtrahend - borrow_in` and return
/// `(result, C, DC, OV)`.
///
/// * **C**: PIC18-style "no-borrow" -- set when the operation
///   completed without requiring a borrow (i.e. when
///   `minuend >= subtrahend + borrow_in`).
/// * **DC**: nibble no-borrow.
/// * **OV**: signed overflow on subtract (different-sign
///   inputs that produce a result whose sign disagrees with
///   the minuend).
fn sub_byte(minuend: u8, subtrahend: u8, borrow_in: bool) -> (u8, bool, bool, bool) {
    let bin = borrow_in as i16;
    let result_full = minuend as i16 - subtrahend as i16 - bin;
    let result = result_full as u8;
    let c = result_full >= 0;
    let dc_full = (minuend & 0x0F) as i16 - (subtrahend & 0x0F) as i16 - bin;
    let dc = dc_full >= 0;
    let m_sign = minuend & 0x80;
    let s_sign = subtrahend & 0x80;
    let r_sign = result & 0x80;
    let ov = (m_sign != s_sign) && (m_sign != r_sign);
    (result, c, dc, ov)
}

/// Resolve an f-operand into a 12-bit data-memory address using
/// the operand's `a` bit and (for `a=BankSelected`) BSR.
fn resolve_f(core: &Core, f: u8, a: Access) -> Address {
    let bank_selected = matches!(a, Access::BankSelected);
    core.memory.resolve(f, bank_selected, read_bsr(core))
}

fn read_f(core: &mut Core, f: u8, a: Access) -> u8 {
    let addr = resolve_f(core, f, a);
    read_addr(core, addr)
}

/// Read one byte from a 12-bit data-memory address.  If the
/// address is one of the 15 FSR virtual slots
/// (INDFn / POSTINCn / POSTDECn / PREINCn / PLUSWn), the access
/// is redirected to `*FSRn` and the FSR side effect commits
/// at the silicon-correct time per DS39632E §5.5.4 -- POST*
/// commits after the read; PRE commits inline during target
/// resolution so the read sees the post-increment pointer.
/// Otherwise it's a plain `Memory::read_raw`.
fn read_addr(core: &mut Core, addr: Address) -> u8 {
    let (target, pending) = resolve_target_no_commit(core, addr);
    let value = core.memory.read_raw(target);
    if let Some((fsr, new_fsr)) = pending {
        commit_fsr(core, fsr, new_fsr);
    }
    value
}

/// Pending FSR mutation: `(fsr, new_value)` where `new_value` is
/// what FSRn should hold after the instruction's operand access
/// completes.  Returned by [`resolve_target_no_commit`] so RMW
/// instructions can take the mutation once at end-of-instruction
/// rather than per memory access (per gpsim's `fsr_state`
/// behaviour).
type PendingFsrUpdate = (FsrIndex, u16);

/// Resolve an operand address into its underlying RAM target.
/// Returns `(target, Some(fsr, new))` when `addr` is a virtual
/// FSR slot whose mode mutates the pointer AFTER the access
/// (POSTINCn / POSTDECn): `Some` is the deferred mutation the
/// caller must commit (via [`commit_fsr`]) exactly once at
/// end-of-instruction.  Returns `None` for modes that don't
/// need a deferred commit (Indirect / PlusW), and ALSO for
/// PreIncrement -- which silicon-correct semantics require to
/// happen BEFORE the access ("FSR is incremented by 1, then
/// used in the operation" per DS39632E §5.5.4).  PreIncrement's
/// FSR write is therefore committed inline here, and the
/// returned target reflects the post-increment FSR value.
fn resolve_target_no_commit(
    core: &mut Core,
    addr: Address,
) -> (Address, Option<PendingFsrUpdate>) {
    let Some((fsr, mode)) = classify_fsr_indirect(addr.as_u16()) else {
        return (addr, None);
    };
    let cur_l = core.memory.read_raw(Address::from_raw(fsr_low_addr(fsr)));
    let cur_h = core.memory.read_raw(Address::from_raw(fsr_high_addr(fsr))) & 0x0F;
    let cur = ((cur_h as u16) << 8) | cur_l as u16;

    match mode {
        FsrAccessMode::Indirect => (Address::from_raw(cur), None),
        FsrAccessMode::PostIncrement => (
            Address::from_raw(cur),
            Some((fsr, cur.wrapping_add(1) & 0x0FFF)),
        ),
        FsrAccessMode::PostDecrement => (
            Address::from_raw(cur),
            Some((fsr, cur.wrapping_sub(1) & 0x0FFF)),
        ),
        FsrAccessMode::PreIncrement => {
            // PRE-mutate inline so the access reads/writes the
            // updated pointer's target.  Matters for the
            // self-referential corner case where FSR points at
            // its own H/L SFR -- e.g. FSR0=0xFE8 followed by
            // PREINC0 reads *0xFE9 = FSR0L AFTER its update,
            // returning 0xE9 (the new low byte), not 0xE8.
            let new_fsr = cur.wrapping_add(1) & 0x0FFF;
            commit_fsr(core, fsr, new_fsr);
            (Address::from_raw(new_fsr), None)
        }
        FsrAccessMode::PlusW => {
            let w = read_w(core);
            let signed = w as i8 as i32;
            let target = ((cur as i32).wrapping_add(signed) as u16) & 0x0FFF;
            (Address::from_raw(target), None)
        }
    }
}

/// Commit a deferred FSR mutation produced by
/// [`resolve_target_no_commit`].
fn commit_fsr(core: &mut Core, fsr: FsrIndex, new_fsr: u16) {
    core.memory
        .write_raw(Address::from_raw(fsr_low_addr(fsr)), new_fsr as u8);
    core.memory.write_raw(
        Address::from_raw(fsr_high_addr(fsr)),
        ((new_fsr >> 8) as u8) & 0x0F,
    );
}

/// Mask away unimplemented bits when writing to an SFR that has
/// some.  Real silicon reads back 0 for those positions
/// regardless of what the firmware wrote (the silicon literally
/// has no storage for them); we apply the mask at write time so
/// `read_raw` returns the silicon-correct value without per-SFR
/// read-side hooks.
///
/// This table covers the *architecturally* documented
/// unimplemented bits per DS39632E Table 5-1 / Register 4-1 /
/// Register 4-2 / §5.4 / §6.3 -- bits whose silicon behaviour is
/// "always read 0" regardless of peripheral configuration.
/// Peripheral SFRs whose bits become inactive only because the
/// peripheral itself is disabled are NOT included; those are
/// modelled by the peripheral wrappers in P2 via
/// `write_byte_through_peripherals`.
const fn sfr_write_mask(addr: u16) -> u8 {
    match addr {
        // STATUS<7:5> unimplemented (Register 5-2).
        STATUS_ADDR => STATUS_VALID_MASK,
        // BSR is a 4-bit register; <7:4> unimplemented (§5.3.2).
        BSR_ADDR => 0x0F,
        // RCON<5> unimplemented (Register 4-1).
        0xFD0 => 0xDF,
        // WDTCON<7:1> unimplemented; only SWDTEN at bit 0 is alive.
        0xFD1 => 0x01,
        // EECON1 bit 5 unimplemented (Register 6-1).
        0xFA6 => 0xDF,
        // EECON2 is not a physical register -- per DS39632E
        // §6.2.1, reads return 0 and writes are consumed by
        // the EE-unlock state machine.  Masking writes to 0x00
        // emulates the read-as-zero contract; the unlock-
        // sequence side effect is the P2 EEPROM peripheral's
        // responsibility.
        0xFA7 => 0x00,
        // FSR0H / FSR1H / FSR2H high nibbles unimplemented
        // (12-bit FSRs; only <3:0> alive in the H register).
        0xFEA | 0xFE2 | 0xFDA => 0x0F,
        // INTCON3 bits 5 and 2 unimplemented (Register 9-3).
        0xFF0 => 0xDB,
        // INTCON2 bits 3 and 1 unimplemented (Register 9-2).
        0xFF1 => 0xF5,
        // TBLPTRU<7:6> unimplemented (TBLPTR is 22 bits; only
        // <5:0> live in TBLPTRU per DS39632E §6.2.3).
        0xFF8 => 0x3F,
        // PCLATU<7:5> unimplemented (PC is 21 bits; only <4:0>
        // alive in PCLATU per DS39632E §5.1.1).
        0xFFB => 0x1F,
        // STKPTR<5> unimplemented (Register 5-1).
        0xFFC => 0xDF,
        // TOSU<7:5> unimplemented (TOS is 21 bits, top 5 bits
        // in TOSU<4:0> per DS39632E §5.1.2.1).
        0xFFF => 0x1F,
        _ => 0xFF,
    }
}

fn write_f(core: &mut Core, f: u8, a: Access, value: u8) {
    let addr = resolve_f(core, f, a);
    write_addr(core, addr, value);
}

/// Write `value` to a 12-bit data-memory address, applying
/// `sfr_write_mask` so unimplemented bits are stripped before
/// the byte lands in the backing array.  Used by MOVFF / LFSR
/// and the dispatch arms whose operands carry the absolute
/// address directly.
///
/// FSR virtual slots (INDFn / POSTINCn / POSTDECn / PREINCn /
/// PLUSWn) are redirected to `*FSRn`.  POSTINC / POSTDEC commit
/// the FSR mutation after the write; PRE commits inline during
/// target resolution (so the write goes to the post-increment
/// pointer).  The `sfr_write_mask` is applied to the
/// *underlying* target, not the virtual slot's address.
///
/// **Known gap:** when the underlying FSR-indirect target
/// happens to be STATUS and the calling instruction is flag-
/// affecting (e.g. `CLRF INDF0` with FSR0 = STATUS), the
/// dispatch's STATUS-skip check sees the operand address (the
/// virtual slot, not STATUS) and the data write goes through
/// here -- clobbering the flag update.  Real DLCP firmware
/// doesn't combine those, so it's deferred (tracked via
/// TaskCreate #14's neighbour).
fn write_addr(core: &mut Core, addr: Address, value: u8) {
    let (target, pending) = resolve_target_no_commit(core, addr);
    core.memory
        .write_raw(target, value & sfr_write_mask(target.as_u16()));
    if let Some((fsr, new_fsr)) = pending {
        commit_fsr(core, fsr, new_fsr);
    }
}

/// Write `value` to the destination implied by a byte-oriented
/// op's `d` bit: W (`Dest::W`) or the f-operand (`Dest::F`).
fn write_dest(core: &mut Core, d: Dest, f: u8, a: Access, value: u8) {
    match d {
        Dest::W => write_w(core, value),
        Dest::F => write_f(core, f, a, value),
    }
}

/// Variant of [`write_dest`] for instructions that update STATUS
/// flags as part of their semantics.  Per DS39632E §5.3.6, when
/// STATUS is the destination of a flag-affecting instruction,
/// the result is *not* written -- the flag update from the
/// op's STATUS-bit math is the sole STATUS change that lands.
/// Otherwise the write would clobber the just-set bits.
fn write_dest_preserve_status_flags(
    core: &mut Core,
    d: Dest,
    f: u8,
    a: Access,
    value: u8,
) {
    let target = match d {
        Dest::W => Address::from_raw(WREG_ADDR),
        Dest::F => resolve_f(core, f, a),
    };
    if target.as_u16() == STATUS_ADDR {
        return;
    }
    match d {
        Dest::W => write_w(core, value),
        Dest::F => write_addr(core, target, value),
    }
}

/// Fatal executor error.  Non-fatal conditions (skip-not-taken,
/// overflow flags, etc.) are signalled through STATUS / RCON
/// inside the model — only the cases below tear the run down.
#[derive(Copy, Clone, Eq, PartialEq, Debug)]
pub enum ExecError {
    /// PC is past the end of the variant's program memory and
    /// has nothing to fetch.  Real silicon wraps; the executor
    /// surfaces this loudly so a runaway test (typically a
    /// missing GOTO at the end of an inline test program) shows
    /// up instead of looping at PC=0 silently.
    PcOutOfBounds(u32),
    /// Decoder produced [`Instruction::Reserved`] — opcode bits
    /// don't match any documented PIC18 instruction.
    Reserved(u16),
    /// Instruction variant not yet wired into the dispatch.  Goes
    /// away as P1.8b lands more instruction categories; once the
    /// match is exhaustive this variant becomes unreachable.
    Unimplemented(Instruction),
}

/// `true` if `word1` is the first half of one of the four
/// 2-word PIC18 opcodes (MOVFF, CALL, LFSR, GOTO) -- i.e. the
/// instruction needs a real `word2` from flash and the executor
/// must not fall back on the 0xFFFF sentinel.
///
/// Encodings (DS39632E §26):
///   - MOVFF: `1100 ffff ffff ffff`         → word1 high4 = 0xC
///   - CALL : `1110 110s kkkk kkkk`         → word1 high8 ∈ {0xEC, 0xED}
///   - LFSR : `1110 1110 00ff kkkk`, with
///              bits 7..6 = 00 AND
///              bits 5..4 ∈ {00, 01, 10}    → only a *subset* of 0xEE prefixes
///   - GOTO : `1110 1111 kkkk kkkk`         → word1 high8 = 0xEF
///
/// LFSR's stricter shape matters because the decoder rejects
/// invalid `0xEE` prefixes as `Instruction::Reserved` with
/// `byte_count=2` (single-word).  A naive `high8 == 0xEE`
/// predicate would over-match (e.g. `0xEE30`, `0xEE40`,
/// `0xEEFF`) and falsely surface PcOutOfBounds on partial fetch
/// where the correct outcome is "decode as Reserved".
const fn opcode_needs_word2(word1: u16) -> bool {
    let high4 = (word1 >> 12) & 0xF;
    if high4 == 0xC {
        return true;
    }
    let high8 = (word1 >> 8) & 0xFF;
    match high8 {
        0xEC | 0xED | 0xEF => true, // CALL / GOTO -- always 2-word.
        0xEE => {
            // LFSR validity: word1 reserved bits must be clear,
            // and the FSR index field (bits 5..4) must encode
            // FSR0 / FSR1 / FSR2, not the reserved 0b11.
            (word1 & 0x00C0) == 0 && ((word1 >> 4) & 0b11) != 0b11
        }
        _ => false,
    }
}

/// Step the core by one instruction.  Returns the Tcy cost of
/// the instruction on success.
pub fn step(core: &mut Core, stack: &mut Stack) -> Result<u8, ExecError> {
    let _ = stack; // kept in the signature even though P1.8b's
    // initial NOP-only dispatch doesn't touch the stack — control-
    // flow instructions land in subsequent commits.

    let pc = core.pc();
    let pc_idx = pc as usize;
    let flash = core.flash();

    // PC must have at least one full word ahead.
    if pc_idx + 1 >= flash.len() {
        return Err(ExecError::PcOutOfBounds(pc));
    }
    let word1 = u16::from_le_bytes([flash[pc_idx], flash[pc_idx + 1]]);

    // The decoder also wants `word2`.  If it can't be read --
    // we're at the very last word of flash -- and word1 is the
    // first half of a 2-word opcode, refuse to execute: the
    // synthetic sentinel would silently fabricate continuation
    // bits, OR (in LFSR's case) make the decoder return
    // Reserved instead of surfacing the real fetch problem.
    // We use a word1-only predicate because LFSR with an
    // invalid word2 sentinel decodes as Reserved + byte_count=2,
    // so a post-decode `byte_count == 4` check would miss it.
    let word2_available = pc_idx + 3 < flash.len();
    if !word2_available && opcode_needs_word2(word1) {
        return Err(ExecError::PcOutOfBounds(pc));
    }
    let word2 = if word2_available {
        u16::from_le_bytes([flash[pc_idx + 2], flash[pc_idx + 3]])
    } else {
        0xFFFF
    };

    let (instr, byte_count) = decode(word1, word2);
    core.set_pc(pc.wrapping_add(byte_count));

    match instr {
        Instruction::Nop => {
            core.advance_cycles(1);
            Ok(1)
        }
        // PIC18 hardware decodes a stray second-word continuation
        // (`1111 xxxx xxxx xxxx`) as NOP; mirror that behaviour
        // rather than erroring, since erased flash + a misaligned
        // jump can land on one and the firmware still expects to
        // recover.
        Instruction::NopContinuation { .. } => {
            core.advance_cycles(1);
            Ok(1)
        }
        // ---------------- literal / data move (1 Tcy each) -------
        Instruction::MovLw { k } => {
            write_w(core, k);
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::Movwf { a, f } => {
            let w = read_w(core);
            write_f(core, f, a, w);
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::Movf { d, a, f } => {
            // MOVF f, d, a -- read f, set Z/N, write to W (d=W)
            // or back to f (d=F).
            //
            // FSR mutation contract (per gpsim's `fsr_state` +
            // DS39632E §5.5.4): the FSR side effect commits
            // exactly ONCE per instruction.  POST* modes
            // commit AFTER the operand access; PRE commits
            // BEFORE (handled inline by
            // `resolve_target_no_commit`, which returns
            // `pending = None` for that mode).  Naively
            // chaining `read_f` + `write_addr` would commit
            // twice for d=F+POST*, advancing the FSR by 2
            // instead of 1.  So we resolve the operand once,
            // do read + (conditional) write against the same
            // target, and commit the pending mutation once at
            // the end (a no-op for PRE / Indirect / PlusW).
            //
            // STATUS-skip per §5.3.6 still applies: when d=F
            // and the resolved target is STATUS, the result
            // write is dropped so the flag update stands.
            let operand_addr = resolve_f(core, f, a);
            let (target, pending) = resolve_target_no_commit(core, operand_addr);
            let v = core.memory.read_raw(target);
            set_status_zn(core, v);
            match d {
                Dest::W => write_w(core, v),
                Dest::F => {
                    if target.as_u16() != STATUS_ADDR {
                        core.memory
                            .write_raw(target, v & sfr_write_mask(target.as_u16()));
                    }
                }
            }
            if let Some((fsr, new_fsr)) = pending {
                commit_fsr(core, fsr, new_fsr);
            }
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::MovLb { k } => {
            // MOVLB loads BSR<3:0> with k<3:0>; bits 7..4 stay 0.
            write_bsr(core, k);
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::Setf { a, f } => {
            // SETF f -- write 0xFF to the f-operand byte.  No
            // STATUS flag updates per DS39632E §26 SETF; if f
            // happens to be STATUS, the unimplemented-bit mask
            // in write_f narrows 0xFF to 0x1F (the implemented
            // bits all get set; bits 7..5 stay 0).
            write_f(core, f, a, 0xFF);
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::Clrf { a, f } => {
            // CLRF f -- clear the f-operand to 0 AND set Z=1.
            // Z is the only flag affected (DS39632E §26).
            // Per §5.3.6, when f=STATUS the result-write of 0
            // would clobber the Z update, so skip the write
            // and let only the flag update land.
            let target = resolve_f(core, f, a);
            if target.as_u16() != STATUS_ADDR {
                write_addr(core, target, 0);
            }
            set_status_bits(core, STATUS_Z, true);
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::Movff { src, dst } => {
            // MOVFF src, dst -- copy one byte between two
            // 12-bit data-memory addresses; 2 Tcy.  No flag
            // updates (DS39632E §26 MOVFF).  Both src and dst
            // route through `read_addr` / `write_addr`, so
            // either or both being an FSR virtual slot
            // (POSTINC0 → POSTDEC1 etc.) triggers indirection
            // + FSRn mutation per §5.5.4.  Silicon errata
            // notes that dst = PCL / TOSU / TOSH / TOSL is
            // undefined; the simulator just writes through and
            // lets the mask handle whatever lands.
            let v = read_addr(core, Address::from_raw(src));
            write_addr(core, Address::from_raw(dst), v);
            core.advance_cycles(2);
            Ok(2)
        }
        Instruction::Lfsr { fsr, k } => {
            // LFSR fsr, k (12-bit literal) -- load FSRnH:FSRnL
            // with k.  No flags affected; 2 Tcy.  The high
            // nibble of k is at most 0xF; the FSRnH mask
            // (0x0F) makes the bound explicit at write time.
            let (fsrh, fsrl) = match fsr {
                FsrIndex::Fsr0 => (0xFEAu16, 0xFE9u16),
                FsrIndex::Fsr1 => (0xFE2, 0xFE1),
                FsrIndex::Fsr2 => (0xFDA, 0xFD9),
            };
            write_addr(core, Address::from_raw(fsrh), (k >> 8) as u8);
            write_addr(core, Address::from_raw(fsrl), k as u8);
            core.advance_cycles(2);
            Ok(2)
        }
        // ---------------- byte-oriented arithmetic (1 Tcy each) -
        Instruction::AddWf { d, a, f } => {
            // ADDWF f, d, a: result = f + W.  STATUS C/DC/Z/OV/N.
            let w = read_w(core);
            execute_arith_with_dest(core, d, a, f, |fv| add_byte(fv, w, false));
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::AddWfC { d, a, f } => {
            // ADDWFC f, d, a: result = f + W + C.  STATUS C/DC/Z/OV/N.
            let w = read_w(core);
            let cin = read_status(core) & STATUS_C != 0;
            execute_arith_with_dest(core, d, a, f, |fv| add_byte(fv, w, cin));
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::Subwf { d, a, f } => {
            // SUBWF f, d, a: result = f - W.  C set when f >= W
            // (no borrow).  STATUS C/DC/Z/OV/N.
            let w = read_w(core);
            execute_arith_with_dest(core, d, a, f, |fv| sub_byte(fv, w, false));
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::SubwfB { d, a, f } => {
            // SUBWFB f, d, a: result = f - W - !C.  STATUS
            // C/DC/Z/OV/N.
            let w = read_w(core);
            let bin = read_status(core) & STATUS_C == 0;
            execute_arith_with_dest(core, d, a, f, |fv| sub_byte(fv, w, bin));
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::SubFwb { d, a, f } => {
            // SUBFWB f, d, a: result = W - f - !C.  STATUS
            // C/DC/Z/OV/N.
            let w = read_w(core);
            let bin = read_status(core) & STATUS_C == 0;
            execute_arith_with_dest(core, d, a, f, |fv| sub_byte(w, fv, bin));
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::Incf { d, a, f } => {
            // INCF f, d, a: result = f + 1.  STATUS C/DC/Z/OV/N.
            execute_arith_with_dest(core, d, a, f, |fv| add_byte(fv, 1, false));
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::Decf { d, a, f } => {
            // DECF f, d, a: result = f - 1.  STATUS C/DC/Z/OV/N.
            execute_arith_with_dest(core, d, a, f, |fv| sub_byte(fv, 1, false));
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::Negf { a, f } => {
            // NEGF f, a: result = -f (= 0 - f, two's complement).
            // No `d` -- result always lands in f.  STATUS
            // C/DC/Z/OV/N.  NEGF 0x80 sets OV=1 (the only fixed
            // point of negation in 8-bit signed).
            let operand_addr = resolve_f(core, f, a);
            let (target, pending) = resolve_target_no_commit(core, operand_addr);
            let f_value = core.memory.read_raw(target);
            let (result, c, dc, ov) = sub_byte(0, f_value, false);
            set_status_arith(core, result, c, dc, ov);
            if target.as_u16() != STATUS_ADDR {
                core.memory
                    .write_raw(target, result & sfr_write_mask(target.as_u16()));
            }
            if let Some((fsr, new_fsr)) = pending {
                commit_fsr(core, fsr, new_fsr);
            }
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::Mulwf { a, f } => {
            // MULWF f, a: PRODH:PRODL = W * f (8x8 unsigned).
            // No flags affected.  PRODL/PRODH have all 8 bits
            // implemented, so a plain raw write is silicon-
            // correct (no mask needed).  Single read of f via
            // `read_f` so FSR side effects (if any) commit
            // exactly once.
            let w = read_w(core);
            let f_value = read_f(core, f, a);
            let prod = w as u16 * f_value as u16;
            core.memory
                .write_raw(Address::from_raw(PRODL_ADDR), prod as u8);
            core.memory
                .write_raw(Address::from_raw(PRODH_ADDR), (prod >> 8) as u8);
            core.advance_cycles(1);
            Ok(1)
        }
        // ---------------- literal arithmetic (1 Tcy each) -------
        Instruction::AddLw { k } => {
            // ADDLW k: W = W + k.  STATUS C/DC/Z/OV/N.
            let w = read_w(core);
            let (result, c, dc, ov) = add_byte(w, k, false);
            set_status_arith(core, result, c, dc, ov);
            write_w(core, result);
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::SubLw { k } => {
            // SUBLW k: W = k - W (note operand order).  STATUS
            // C/DC/Z/OV/N.
            let w = read_w(core);
            let (result, c, dc, ov) = sub_byte(k, w, false);
            set_status_arith(core, result, c, dc, ov);
            write_w(core, result);
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::MulLw { k } => {
            // MULLW k: PRODH:PRODL = W * k (8x8 unsigned).  No
            // flags affected.
            let w = read_w(core);
            let prod = w as u16 * k as u16;
            core.memory
                .write_raw(Address::from_raw(PRODL_ADDR), prod as u8);
            core.memory
                .write_raw(Address::from_raw(PRODH_ADDR), (prod >> 8) as u8);
            core.advance_cycles(1);
            Ok(1)
        }
        // ---------------- logical / rotate / swap (1 Tcy each) -
        Instruction::AndWf { d, a, f } => {
            // ANDWF f, d, a: result = W & f.  STATUS Z, N.
            let w = read_w(core);
            execute_logical_with_dest(core, d, a, f, |fv| w & fv);
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::IorWf { d, a, f } => {
            // IORWF f, d, a: result = W | f.  STATUS Z, N.
            let w = read_w(core);
            execute_logical_with_dest(core, d, a, f, |fv| w | fv);
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::XorWf { d, a, f } => {
            // XORWF f, d, a: result = W ^ f.  STATUS Z, N.
            let w = read_w(core);
            execute_logical_with_dest(core, d, a, f, |fv| w ^ fv);
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::Comf { d, a, f } => {
            // COMF f, d, a: result = ~f (one's complement).
            // STATUS Z, N.
            execute_logical_with_dest(core, d, a, f, |fv| !fv);
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::Rlcf { d, a, f } => {
            // RLCF f, d, a: rotate f left through C.  New byte:
            //   result = (f << 1) | C_in
            //   C_out = bit 7 of f (the bit shifted out).
            // STATUS C, Z, N.  DC and OV survive untouched.
            let cin = if read_status(core) & STATUS_C != 0 { 1 } else { 0 };
            execute_op_with_dest(core, d, a, f, |core, fv| {
                let result = (fv << 1) | cin;
                set_status_bits(core, STATUS_C, fv & 0x80 != 0);
                set_status_zn(core, result);
                result
            });
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::Rlncf { d, a, f } => {
            // RLNCF f, d, a: rotate f left, no carry.
            //   result = f.rotate_left(1)
            // STATUS Z, N (C left alone).
            execute_logical_with_dest(core, d, a, f, |fv| fv.rotate_left(1));
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::Rrcf { d, a, f } => {
            // RRCF f, d, a: rotate f right through C.
            //   result = (f >> 1) | (C_in << 7)
            //   C_out = bit 0 of f.
            // STATUS C, Z, N.
            let cin = if read_status(core) & STATUS_C != 0 { 0x80 } else { 0 };
            execute_op_with_dest(core, d, a, f, |core, fv| {
                let result = (fv >> 1) | cin;
                set_status_bits(core, STATUS_C, fv & 0x01 != 0);
                set_status_zn(core, result);
                result
            });
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::Rrncf { d, a, f } => {
            // RRNCF f, d, a: rotate f right, no carry.
            execute_logical_with_dest(core, d, a, f, |fv| fv.rotate_right(1));
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::Swapf { d, a, f } => {
            // SWAPF f, d, a: swap the high and low nibbles of f.
            // STATUS NOT affected (DS39632E §26 SWAPF).  Use
            // execute_op_with_dest directly so we skip the
            // implicit Z/N update of execute_logical_with_dest.
            execute_op_with_dest(core, d, a, f, |_core, fv| {
                (fv << 4) | (fv >> 4)
            });
            core.advance_cycles(1);
            Ok(1)
        }
        Instruction::Reserved { word } => Err(ExecError::Reserved(word)),
        other => Err(ExecError::Unimplemented(other)),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::memory::Variant;

    fn k20_core_with_flash(prog: &[u8]) -> Core {
        let mut core = Core::new(Variant::Pic18F25K20);
        core.flash_mut()[..prog.len()].copy_from_slice(prog);
        core
    }

    // 0x0000 is the NOP encoding (`0000 0000 0000 0000`).
    const NOP_BYTES: [u8; 2] = [0x00, 0x00];

    #[test]
    fn step_nop_advances_pc_by_two_and_charges_one_cycle() {
        let mut core = k20_core_with_flash(&NOP_BYTES);
        let mut stack = Stack::new();

        let cycles = step(&mut core, &mut stack).expect("NOP must execute");
        assert_eq!(cycles, 1, "NOP costs 1 Tcy");
        assert_eq!(core.pc(), 0x0002);
        assert_eq!(core.cycles(), 1);
    }

    #[test]
    fn step_two_nops_in_a_row_advance_pc_and_cycles_monotonically() {
        let prog = [0x00, 0x00, 0x00, 0x00];
        let mut core = k20_core_with_flash(&prog);
        let mut stack = Stack::new();

        step(&mut core, &mut stack).unwrap();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.pc(), 0x0004);
        assert_eq!(core.cycles(), 2);
    }

    #[test]
    fn step_treats_nop_continuation_as_nop() {
        // `0xFFFF` decodes as NopContinuation; PIC18 silicon
        // executes it as NOP.  The executor must mirror that —
        // one Tcy, PC advances by 2, no error.
        let mut core = k20_core_with_flash(&[0xFF, 0xFF]);
        let mut stack = Stack::new();

        let cycles = step(&mut core, &mut stack).expect("NopContinuation is silent NOP");
        assert_eq!(cycles, 1);
        assert_eq!(core.pc(), 0x0002);
    }

    #[test]
    fn step_returns_pc_out_of_bounds_when_word1_unfetchable() {
        // Flash is 0x8000 bytes (0x0000..0x8000).  PC=0x8000 is
        // past the last fetchable byte; word1 cannot be assembled.
        let mut core = Core::new(Variant::Pic18F25K20);
        core.set_pc(0x8000);
        let mut stack = Stack::new();

        let err = step(&mut core, &mut stack).unwrap_err();
        match err {
            ExecError::PcOutOfBounds(pc) => assert_eq!(pc, 0x8000),
            other => panic!("expected PcOutOfBounds, got {other:?}"),
        }
        // PC must NOT have advanced (the executor errors before
        // calling set_pc on the partial-fetch path).
        assert_eq!(core.pc(), 0x8000);
    }

    #[test]
    fn step_succeeds_at_last_word_when_instruction_is_single_word() {
        // PC=0x7FFE with a NOP at the last word: word1 fetchable,
        // word2 not fetchable, but decode returns byte_count=2 so
        // the missing word2 is irrelevant.  Step must succeed.
        let mut core = Core::new(Variant::Pic18F25K20);
        let last_word = 0x8000 - 2;
        core.flash_mut()[last_word] = 0x00; // NOP low byte
        core.flash_mut()[last_word + 1] = 0x00; // NOP high byte
        core.set_pc(last_word as u32);
        let mut stack = Stack::new();

        let cycles = step(&mut core, &mut stack).expect("single-word op at last word OK");
        assert_eq!(cycles, 1);
        // PC wraps via set_pc's mask: 0x7FFE + 2 = 0x8000, masked
        // to 0x001F_FFFE leaves 0x8000 — outside flash on this
        // variant, but `step` did its job.
        assert_eq!(core.pc(), 0x8000);
    }

    #[test]
    fn step_returns_pc_out_of_bounds_on_partial_two_word_fetch_goto() {
        // PC=0x7FFE with the first word of a GOTO at the last
        // word: word1=0xEF00 fetchable, word2 unfetchable.  Without
        // the predicate, decode would synthesise word2=0xFFFF and
        // hand back Goto with byte_count=4.
        partial_two_word_fetch_case(&[0x00, 0xEF]);
    }

    #[test]
    fn step_returns_pc_out_of_bounds_on_partial_two_word_fetch_lfsr() {
        // LFSR FSR0, 0: word1=0xEE00, word2=0xF000.  At the last
        // word with word2 unavailable, decode(0xEE00, 0xFFFF)
        // returns *Reserved* (because the sentinel fails LFSR's
        // `word2 & 0xFF00 == 0xF000` check), with byte_count=2 --
        // a post-decode `byte_count == 4` guard would have missed
        // this entirely.
        partial_two_word_fetch_case(&[0x00, 0xEE]);
    }

    #[test]
    fn step_returns_pc_out_of_bounds_on_partial_two_word_fetch_call() {
        // CALL 0, fast=0: word1=0xEC00.
        partial_two_word_fetch_case(&[0x00, 0xEC]);
    }

    #[test]
    fn step_returns_pc_out_of_bounds_on_partial_two_word_fetch_movff() {
        // MOVFF src=0, dst=0: word1=0xC000.
        partial_two_word_fetch_case(&[0x00, 0xC0]);
    }

    fn partial_two_word_fetch_case(word1_bytes: &[u8]) {
        let mut core = Core::new(Variant::Pic18F25K20);
        let last_word = 0x8000 - 2;
        core.flash_mut()[last_word] = word1_bytes[0];
        core.flash_mut()[last_word + 1] = word1_bytes[1];
        core.set_pc(last_word as u32);
        let mut stack = Stack::new();

        let err = step(&mut core, &mut stack).unwrap_err();
        match err {
            ExecError::PcOutOfBounds(pc) => assert_eq!(pc, last_word as u32),
            other => panic!("expected PcOutOfBounds, got {other:?}"),
        }
        // PC must NOT have advanced past the partial fetch.
        assert_eq!(core.pc(), last_word as u32);
    }

    #[test]
    fn opcode_needs_word2_predicate_matches_documented_two_word_set() {
        // Positive: MOVFF / CALL / valid-LFSR / GOTO prefixes.
        for w in [
            0xC000, 0xCFFF, // MOVFF range (high4 = C)
            0xEC00, 0xED00, // CALL (high8 = EC / ED)
            // LFSR: word1 = 1110 1110 00ff kkkk where ff ∈ {00, 01, 10}.
            0xEE00, // LFSR FSR0, k=0
            0xEE0F, // LFSR FSR0, k[11:8] = 0xF
            0xEE1A, // LFSR FSR1, k[11:8] = 0xA
            0xEE2C, // LFSR FSR2, k[11:8] = 0xC
            0xEF00, 0xEFFF, // GOTO (high8 = EF)
        ] {
            assert!(
                opcode_needs_word2(w),
                "0x{w:04X} should be flagged as 2-word"
            );
        }

        // Negative set, three groups:
        //
        //   1. Genuinely-single-word opcodes that share none of
        //      the predicate's high-bit prefixes.
        //   2. The 0xE8..0xEB unallocated range -- decoder
        //      produces Reserved with byte_count = 2.
        //   3. 0xEE-prefixed words that fail LFSR validity --
        //      the decoder also rejects these as Reserved with
        //      byte_count = 2, so the predicate must mirror.
        for w in [
            // Group 1: single-word ops elsewhere in the ISA.
            0x0000, // NOP
            0x0E42, // MOVLW 0x42
            0xD000, // BRA
            0xD800, // RCALL
            0xE000, 0xE700, // BZ..BNN
            0x6E00, // MOVWF
            0x9000, // BCF
            // Group 2: unallocated 0xE8..0xEB.
            0xE800, 0xEB00,
            // Group 3: 0xEE prefixes the decoder rejects as
            // Reserved.
            0xEE40, // bits 7..6 = 01 (reserved)
            0xEE80, // bits 7..6 = 10 (reserved)
            0xEEC0, // bits 7..6 = 11 (reserved)
            0xEE30, // bits 5..4 = 11 (FSR index = 0b11, invalid)
            0xEEFF, // bits 7..6 = 11 AND ff = 11 (doubly reserved)
        ] {
            assert!(
                !opcode_needs_word2(w),
                "0x{w:04X} should NOT be flagged as 2-word"
            );
        }
    }

    #[test]
    fn step_reports_unimplemented_for_not_yet_wired_instruction() {
        // BTG 0x10, 0, ACCESS — encoding 0x7010 (high4=0111
        // bit-oriented BTG; b=0; a=ACCESS; f=0x10).  Not yet
        // wired into the dispatch (bit-oriented ops land in a
        // later P1.8b commit).  This test pins the Unimplemented
        // arm and will need updating (changed to assert successful
        // exec) when BTG lands.
        let mut core = k20_core_with_flash(&[0x10, 0x70]);
        let mut stack = Stack::new();

        let err = step(&mut core, &mut stack).unwrap_err();
        assert!(
            matches!(err, ExecError::Unimplemented(Instruction::Btg { .. })),
            "expected Unimplemented(Btg), got {err:?}"
        );
        // PC should still have advanced (the dispatch happens after
        // the fetch+set_pc, so the caller can recover by retrying
        // from a new program counter).
        assert_eq!(core.pc(), 0x0002);
        // Cycle counter stays at 0 — Unimplemented didn't consume
        // a Tcy because no instruction actually ran.
        assert_eq!(core.cycles(), 0);
    }

    // ------------------------------------------------------------
    // Literal / data-move instructions: MOVLW, MOVWF, MOVF, MOVLB.
    // ------------------------------------------------------------

    #[test]
    fn movlw_loads_literal_into_w() {
        // MOVLW 0x42 — opcode 0x0E42.
        let mut core = k20_core_with_flash(&[0x42, 0x0E]);
        let mut stack = Stack::new();
        let cycles = step(&mut core, &mut stack).unwrap();
        assert_eq!(cycles, 1);
        assert_eq!(read_w(&core), 0x42);
        assert_eq!(core.pc(), 0x0002);
    }

    #[test]
    fn movlw_does_not_touch_status() {
        // MOVLW must not affect Z / N / C / DC / OV.
        let mut core = k20_core_with_flash(&[0x00, 0x0E]); // MOVLW 0x00
        let mut stack = Stack::new();
        // Pre-set every status bit to 1; MOVLW must leave them alone.
        core.memory
            .write_raw(Address::from_raw(STATUS_ADDR), STATUS_VALID_MASK);
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_status(&core), STATUS_VALID_MASK);
        assert_eq!(read_w(&core), 0x00);
    }

    #[test]
    fn movwf_stores_w_into_access_bank_low() {
        // Pre-load: MOVLW 0x55, MOVWF 0x10, ACCESS  (f=0x10 < 0x60 → bank 0 RAM).
        // MOVLW 0x55 = 0x0E55; MOVWF f, ACCESS = 0x6E10 (high8 = 0x6E, low = f).
        let mut core = k20_core_with_flash(&[0x55, 0x0E, 0x10, 0x6E]);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap(); // MOVLW
        step(&mut core, &mut stack).unwrap(); // MOVWF
        // f=0x10 with a=ACCESS lands at bank 0 offset 0x10 → addr 0x010.
        assert_eq!(core.memory.read_raw(Address::from_raw(0x010)), 0x55);
        // W is unchanged.
        assert_eq!(read_w(&core), 0x55);
    }

    #[test]
    fn movwf_stores_w_into_sfr_window_via_access_bank() {
        // f=0x80 with a=ACCESS routes to 0xF80 (Access-Bank high
        // half).  Use 0xC0 → 0xFC0; that's an unused SFR slot on
        // both variants but the executor doesn't know that, just
        // that the byte lands at addr 0xFC0.
        // MOVLW 0xAA = 0x0EAA; MOVWF 0xC0, ACCESS = 0x6EC0.
        let mut core = k20_core_with_flash(&[0xAA, 0x0E, 0xC0, 0x6E]);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFC0)), 0xAA);
    }

    #[test]
    fn movwf_with_bank_selected_uses_bsr() {
        // Set BSR=3; MOVWF 0x40, BANKED → addr (3<<8)|0x40 = 0x340.
        // MOVLW 0x77 = 0x0E77; MOVWF 0x40, BANKED = 0x6F40.
        let mut core = k20_core_with_flash(&[0x77, 0x0E, 0x40, 0x6F]);
        let mut stack = Stack::new();
        write_bsr(&mut core, 3);
        step(&mut core, &mut stack).unwrap(); // MOVLW
        step(&mut core, &mut stack).unwrap(); // MOVWF
        assert_eq!(core.memory.read_raw(Address::from_raw(0x340)), 0x77);
    }

    #[test]
    fn movf_to_w_loads_byte_and_sets_z_when_zero() {
        // RAM[0x10] = 0x00 (default); MOVF 0x10, W, ACCESS = 0x5010.
        let mut core = k20_core_with_flash(&[0x10, 0x50]);
        let mut stack = Stack::new();
        // Pre-clear STATUS so we can see the Z bit appear.
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), 0);
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_w(&core), 0x00);
        assert!(read_status(&core) & STATUS_Z != 0, "Z must be set");
        assert!(read_status(&core) & STATUS_N == 0, "N must be clear");
    }

    #[test]
    fn movf_to_w_sets_n_for_negative_byte() {
        // RAM[0x20] = 0x80 → bit 7 set → N=1.
        // MOVF 0x20, W, ACCESS = 0x5020.
        let mut core = k20_core_with_flash(&[0x20, 0x50]);
        core.memory.write_raw(Address::from_raw(0x020), 0x80);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_w(&core), 0x80);
        assert!(read_status(&core) & STATUS_N != 0, "N must be set");
        assert!(read_status(&core) & STATUS_Z == 0, "Z must be clear");
    }

    #[test]
    fn movf_to_w_with_nonzero_positive_clears_z_and_n() {
        // RAM[0x30] = 0x42; MOVF 0x30, W, ACCESS = 0x5030.
        let mut core = k20_core_with_flash(&[0x30, 0x50]);
        core.memory.write_raw(Address::from_raw(0x030), 0x42);
        // Pre-set Z + N so we can confirm they get cleared.
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), STATUS_Z | STATUS_N);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_w(&core), 0x42);
        assert!(read_status(&core) & STATUS_Z == 0);
        assert!(read_status(&core) & STATUS_N == 0);
    }

    #[test]
    fn movf_to_f_writes_back_and_still_updates_status() {
        // The "MOVF f, F" idiom is firmware shorthand for "test
        // f without disturbing W".  The byte lands back in f and
        // STATUS Z / N reflect it; W stays whatever it was.
        // MOVF 0x10, F, ACCESS = 0x5210 (d=F has bit 9 set).
        let mut core = k20_core_with_flash(&[0x10, 0x52]);
        core.memory.write_raw(Address::from_raw(0x010), 0x00);
        write_w(&mut core, 0xFF); // marker: must remain 0xFF.
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), 0);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0x010)), 0x00);
        assert_eq!(read_w(&core), 0xFF, "W must be untouched by MOVF f, F");
        assert!(read_status(&core) & STATUS_Z != 0);
    }

    // ------------------------------------------------------------
    // SETF / CLRF / MOVFF / LFSR -- complete the data-movement
    // category.
    // ------------------------------------------------------------

    #[test]
    fn setf_writes_all_ones_to_access_bank_low_register() {
        // SETF f, a=ACCESS: encoding 0110 1000 ffff ffff = 0x68ff.
        // f=0x10 → Access-Bank low → addr 0x010.
        let mut core = k20_core_with_flash(&[0x10, 0x68]);
        let mut stack = Stack::new();
        let cycles = step(&mut core, &mut stack).unwrap();
        assert_eq!(cycles, 1);
        assert_eq!(core.memory.read_raw(Address::from_raw(0x010)), 0xFF);
    }

    #[test]
    fn setf_to_status_lands_only_implemented_bits() {
        // SETF STATUS, ACCESS: f=0xD8 → 0xFD8.  STATUS_VALID_MASK
        // narrows the 0xFF write to 0x1F.  SETF doesn't touch
        // flags itself, so the result IS the new STATUS.
        let mut core = k20_core_with_flash(&[0xD8, 0x68]);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_status(&core), STATUS_VALID_MASK);
    }

    #[test]
    fn clrf_writes_zero_and_sets_z() {
        // CLRF f, a=ACCESS: encoding 0110 1010 ffff ffff = 0x6Aff.
        // f=0x20 → addr 0x020.  Pre-load 0xAA so we see it clear.
        let mut core = k20_core_with_flash(&[0x20, 0x6A]);
        core.memory.write_raw(Address::from_raw(0x020), 0xAA);
        // Pre-clear STATUS so we see Z appear.
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), 0);
        let mut stack = Stack::new();
        let cycles = step(&mut core, &mut stack).unwrap();
        assert_eq!(cycles, 1);
        assert_eq!(core.memory.read_raw(Address::from_raw(0x020)), 0x00);
        assert!(read_status(&core) & STATUS_Z != 0, "Z must be set");
    }

    #[test]
    fn clrf_to_status_preserves_other_flags_and_sets_z() {
        // Per DS39632E §5.3.6: a flag-affecting op targeting
        // STATUS drops the result write -- only the flag
        // update lands.  CLRF only affects Z, so C/DC/OV/N
        // must survive a `CLRF STATUS, ACCESS`.
        // f=0xD8 → STATUS at 0xFD8.  Encoding 0x6AD8.
        let mut core = k20_core_with_flash(&[0xD8, 0x6A]);
        // Pre-set every implemented STATUS bit; CLRF should
        // leave C/DC/OV/N alone and Z stays set (was already 1).
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), STATUS_VALID_MASK);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        // C, DC, OV, N must survive; Z stays set.
        assert!(read_status(&core) & STATUS_C != 0);
        assert!(read_status(&core) & STATUS_DC != 0);
        assert!(read_status(&core) & STATUS_OV != 0);
        assert!(read_status(&core) & STATUS_N != 0);
        assert!(read_status(&core) & STATUS_Z != 0);
    }

    #[test]
    fn movff_copies_byte_between_arbitrary_data_memory_addresses() {
        // MOVFF 0x123, 0x456 -- 2-word encoding:
        //   word1 = 1100 ffff ffff ffff = 0xC123
        //   word2 = 1111 ffff ffff ffff = 0xF456
        let mut core = k20_core_with_flash(&[0x23, 0xC1, 0x56, 0xF4]);
        // Source byte at 0x123 (bank 1 offset 0x23).
        core.memory.write_raw(Address::from_raw(0x123), 0xA5);
        let mut stack = Stack::new();
        let cycles = step(&mut core, &mut stack).unwrap();
        assert_eq!(cycles, 2, "MOVFF costs 2 Tcy (2-word op)");
        assert_eq!(core.pc(), 0x0004, "PC advances by 4 bytes");
        // Source unchanged, destination has the copy.
        assert_eq!(core.memory.read_raw(Address::from_raw(0x123)), 0xA5);
        assert_eq!(core.memory.read_raw(Address::from_raw(0x456)), 0xA5);
    }

    #[test]
    fn movff_to_sfr_with_unimplemented_bits_applies_mask() {
        // MOVFF 0x100 → STATUS (0xFD8): if source byte has
        // bits 7..5 set, the SFR mask must strip them so STATUS
        // only retains bits 4..0.
        // word1 = 0xC100 (src=0x100), word2 = 0xFFD8 (dst=0xFD8;
        // upper nibble of word2 is don't-care, decoder takes only
        // the low 12 bits).
        let mut core = k20_core_with_flash(&[0x00, 0xC1, 0xD8, 0xFF]);
        core.memory.write_raw(Address::from_raw(0x100), 0xFF);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_status(&core), STATUS_VALID_MASK);
    }

    #[test]
    fn lfsr_loads_12_bit_literal_into_fsr0() {
        // LFSR FSR0, 0x123 -- 2-word encoding:
        //   word1 = 1110 1110 00ff kkkk where ff=0 (FSR0), k[11:8]=0x1
        //         = 1110 1110 0000 0001 = 0xEE01
        //   word2 = 1111 0000 kkkk kkkk where k[7:0]=0x23
        //         = 1111 0000 0010 0011 = 0xF023
        let mut core = k20_core_with_flash(&[0x01, 0xEE, 0x23, 0xF0]);
        let mut stack = Stack::new();
        let cycles = step(&mut core, &mut stack).unwrap();
        assert_eq!(cycles, 2, "LFSR costs 2 Tcy (2-word op)");
        assert_eq!(core.pc(), 0x0004);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFE9)), 0x23);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFEA)), 0x01);
    }

    #[test]
    fn lfsr_loads_into_fsr1_and_fsr2() {
        // LFSR FSR1, 0x4AB and LFSR FSR2, 0x7DE in sequence.
        let mut core = k20_core_with_flash(&[
            // LFSR FSR1, 0x4AB:
            //   word1 = 0xEE14 (ff=01=FSR1, k[11:8]=4)
            //   word2 = 0xF0AB (k[7:0]=AB)
            0x14, 0xEE, 0xAB, 0xF0,
            // LFSR FSR2, 0x7DE:
            //   word1 = 0xEE27 (ff=10=FSR2, k[11:8]=7)
            //   word2 = 0xF0DE (k[7:0]=DE)
            0x27, 0xEE, 0xDE, 0xF0,
        ]);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFE1)), 0xAB);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFE2)), 0x04);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFD9)), 0xDE);
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFDA)), 0x07);
    }

    // ------------------------------------------------------------
    // Byte-oriented arithmetic + STATUS C/DC/OV math.
    // ------------------------------------------------------------

    #[test]
    fn add_byte_helper_reports_carry_out() {
        let (r, c, dc, ov) = add_byte(0xFF, 0x01, false);
        assert_eq!(r, 0x00);
        assert!(c);
        assert!(dc);
        assert!(!ov);
    }

    #[test]
    fn add_byte_helper_reports_signed_overflow() {
        // 0x7F + 0x01 = 0x80 (positive + positive → negative).
        let (r, c, dc, ov) = add_byte(0x7F, 0x01, false);
        assert_eq!(r, 0x80);
        assert!(!c);
        assert!(dc);
        assert!(ov);
    }

    #[test]
    fn sub_byte_helper_reports_no_borrow_when_minuend_ge_subtrahend() {
        // 0x10 - 0x05 = 0x0B.  Byte-level: no borrow → C=1.
        // Nibble-level: low(0x10)=0 - low(0x05)=5 → borrow at
        // the nibble boundary → DC=0 per DS39632E §3.5.2.1
        // ("DC = 0 if a borrow occurred").
        let (r, c, dc, ov) = sub_byte(0x10, 0x05, false);
        assert_eq!(r, 0x0B);
        assert!(c, "C=1 means no byte-level borrow");
        assert!(!dc, "DC=0 because the low nibble required a borrow");
        assert!(!ov);
    }

    #[test]
    fn sub_byte_helper_reports_borrow_when_minuend_lt_subtrahend() {
        // 0x05 - 0x10 = 0xF5 (signed -11).  Byte-level: borrow → C=0.
        // Nibble-level: low(0x05)=5 - low(0x10)=0 → no nibble
        // borrow → DC=1.
        let (r, c, dc, ov) = sub_byte(0x05, 0x10, false);
        assert_eq!(r, 0xF5);
        assert!(!c, "C=0 means byte-level borrow");
        assert!(dc, "DC=1 because the low nibble didn't borrow");
        assert!(!ov);
    }

    #[test]
    fn addwf_w_plus_f_to_w_with_carry_out() {
        // ADDWF 0x10, W, ACCESS: high8 = 0x24, low = 0x10 → 0x2410.
        // W=0xFF, RAM[0x10]=0x01 → result=0x00, C=1, DC=1, Z=1, OV=0.
        let mut core = k20_core_with_flash(&[0x10, 0x24]);
        write_w(&mut core, 0xFF);
        core.memory.write_raw(Address::from_raw(0x010), 0x01);
        // Pre-clear STATUS so we see what gets set.
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), 0);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_w(&core), 0x00);
        // Source f untouched.
        assert_eq!(core.memory.read_raw(Address::from_raw(0x010)), 0x01);
        let s = read_status(&core);
        assert!(s & STATUS_C != 0);
        assert!(s & STATUS_DC != 0);
        assert!(s & STATUS_Z != 0);
        assert!(s & STATUS_OV == 0);
        assert!(s & STATUS_N == 0);
    }

    #[test]
    fn addwf_d_eq_f_writes_back_to_memory() {
        // ADDWF 0x10, F, ACCESS = 0x2610.
        let mut core = k20_core_with_flash(&[0x10, 0x26]);
        write_w(&mut core, 0x05);
        core.memory.write_raw(Address::from_raw(0x010), 0x03);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0x010)), 0x08);
        assert_eq!(read_w(&core), 0x05, "W untouched when d=F");
    }

    #[test]
    fn addwfc_uses_carry_in() {
        // ADDWFC 0x10, W, ACCESS: high8 = 0x20, low = 0x10 → 0x2010.
        // W=0x05, RAM[0x10]=0x03, C=1 → result = 0x09.
        let mut core = k20_core_with_flash(&[0x10, 0x20]);
        write_w(&mut core, 0x05);
        core.memory.write_raw(Address::from_raw(0x010), 0x03);
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), STATUS_C);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_w(&core), 0x09);
    }

    #[test]
    fn subwf_sets_carry_when_minuend_ge_subtrahend() {
        // SUBWF 0x10, W, ACCESS: high8 = 0x5C, low = 0x10 → 0x5C10.
        // result = f - W = 0x10 - 0x03 = 0x0D, C=1.
        let mut core = k20_core_with_flash(&[0x10, 0x5C]);
        write_w(&mut core, 0x03);
        core.memory.write_raw(Address::from_raw(0x010), 0x10);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_w(&core), 0x0D);
        assert!(read_status(&core) & STATUS_C != 0);
    }

    #[test]
    fn subwf_clears_carry_when_borrow_required() {
        // SUBWF 0x10, W, ACCESS: f=0x03 - W=0x10 = -0x0D = 0xF3, C=0.
        let mut core = k20_core_with_flash(&[0x10, 0x5C]);
        write_w(&mut core, 0x10);
        core.memory.write_raw(Address::from_raw(0x010), 0x03);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_w(&core), 0xF3);
        assert!(read_status(&core) & STATUS_C == 0);
        assert!(read_status(&core) & STATUS_N != 0);
    }

    #[test]
    fn subwfb_threads_borrow_through_chain() {
        // SUBWFB 0x10, W, ACCESS: high6 = 010110, d=0, a=0 →
        // high8 = 0x58, low = 0x10 → 0x5810.
        // f=0x10, W=0x05, C_in=0 (borrow=1) → result = 0x10 - 5 - 1 = 0x0A.
        let mut core = k20_core_with_flash(&[0x10, 0x58]);
        write_w(&mut core, 0x05);
        core.memory.write_raw(Address::from_raw(0x010), 0x10);
        // Clear C so borrow_in=1.
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), 0);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_w(&core), 0x0A);
    }

    #[test]
    fn subfwb_subtracts_f_from_w() {
        // SUBFWB 0x10, W, ACCESS: high6=010101, d=0, a=0 → high8 = 0x54, low = 0x10 → 0x5410.
        // result = W - f - !C.  W=0x10, f=0x05, C=1 → 0x10 - 0x05 - 0 = 0x0B.
        let mut core = k20_core_with_flash(&[0x10, 0x54]);
        write_w(&mut core, 0x10);
        core.memory.write_raw(Address::from_raw(0x010), 0x05);
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), STATUS_C);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_w(&core), 0x0B);
    }

    #[test]
    fn incf_increments_f_and_updates_status() {
        // INCF 0x10, F, ACCESS: high8 = 0x2A (high6=001010, d=1, a=0), low = 0x10 → 0x2A10.
        // f=0xFF → 0x00, C=1, Z=1.
        let mut core = k20_core_with_flash(&[0x10, 0x2A]);
        core.memory.write_raw(Address::from_raw(0x010), 0xFF);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0x010)), 0x00);
        let s = read_status(&core);
        assert!(s & STATUS_C != 0);
        assert!(s & STATUS_Z != 0);
    }

    #[test]
    fn decf_decrements_f_and_updates_status() {
        // DECF 0x10, F, ACCESS: high8 = 0x06 (high6=000001, d=1, a=0), low = 0x10 → 0x0610.
        // f=0x01 → 0x00, C=1 (no borrow), Z=1.
        let mut core = k20_core_with_flash(&[0x10, 0x06]);
        core.memory.write_raw(Address::from_raw(0x010), 0x01);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0x010)), 0x00);
        let s = read_status(&core);
        assert!(s & STATUS_C != 0);
        assert!(s & STATUS_Z != 0);
    }

    #[test]
    fn negf_zero_yields_zero_with_z_set() {
        // NEGF 0x10, ACCESS: high8 = 0x6C (high7=0110110, a=0), low = 0x10 → 0x6C10.
        // f=0x00 → 0x00, C=1, Z=1, OV=0, N=0.
        let mut core = k20_core_with_flash(&[0x10, 0x6C]);
        core.memory.write_raw(Address::from_raw(0x010), 0x00);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0x010)), 0x00);
        assert!(read_status(&core) & STATUS_Z != 0);
        assert!(read_status(&core) & STATUS_OV == 0);
    }

    #[test]
    fn negf_0x80_overflows() {
        // NEGF 0x10, ACCESS = 0x6C10.  f=0x80 → -(-128) = +128, but
        // 8-bit signed can't represent +128, so result wraps to 0x80
        // and OV=1 per silicon two's-complement semantics.
        let mut core = k20_core_with_flash(&[0x10, 0x6C]);
        core.memory.write_raw(Address::from_raw(0x010), 0x80);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0x010)), 0x80);
        assert!(read_status(&core) & STATUS_OV != 0);
        assert!(read_status(&core) & STATUS_N != 0);
    }

    #[test]
    fn negf_positive_value_yields_negative() {
        // NEGF 0x10: f=0x05 → -5 → 0xFB.  C=0 (borrow), N=1.
        let mut core = k20_core_with_flash(&[0x10, 0x6C]);
        core.memory.write_raw(Address::from_raw(0x010), 0x05);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0x010)), 0xFB);
        assert!(read_status(&core) & STATUS_C == 0);
        assert!(read_status(&core) & STATUS_N != 0);
    }

    #[test]
    fn mulwf_writes_full_16_bit_product_to_prod_pair() {
        // MULWF 0x10, ACCESS: high8 = 0x02 (high7=0000001, a=0), low = 0x10 → 0x0210.
        // W=0xFF, f=0xFF → 0xFE01.
        let mut core = k20_core_with_flash(&[0x10, 0x02]);
        write_w(&mut core, 0xFF);
        core.memory.write_raw(Address::from_raw(0x010), 0xFF);
        // Pre-set STATUS Z so we can confirm MULWF doesn't touch flags.
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), STATUS_Z);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(PRODL_ADDR)), 0x01);
        assert_eq!(core.memory.read_raw(Address::from_raw(PRODH_ADDR)), 0xFE);
        // STATUS untouched.
        assert_eq!(read_status(&core), STATUS_Z);
    }

    // ---- literal arithmetic ----

    #[test]
    fn addlw_adds_literal_to_w() {
        // ADDLW 0x05: high8 = 0x0F, low = 0x05 → 0x0F05.
        let mut core = k20_core_with_flash(&[0x05, 0x0F]);
        write_w(&mut core, 0x10);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_w(&core), 0x15);
    }

    #[test]
    fn sublw_subtracts_w_from_literal() {
        // SUBLW 0x10: high8 = 0x08, low = 0x10 → 0x0810.
        // W = 0x05 → result = 0x10 - 0x05 = 0x0B (NOT 0x05 - 0x10).
        let mut core = k20_core_with_flash(&[0x10, 0x08]);
        write_w(&mut core, 0x05);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_w(&core), 0x0B);
        assert!(read_status(&core) & STATUS_C != 0, "k > W → no borrow");
    }

    #[test]
    fn mullw_writes_full_16_bit_product() {
        // MULLW 0xFF: high8 = 0x0D, low = 0xFF → 0x0DFF.
        // W = 0xFE → 0xFE * 0xFF = 0xFD02.
        let mut core = k20_core_with_flash(&[0xFF, 0x0D]);
        write_w(&mut core, 0xFE);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(PRODL_ADDR)), 0x02);
        assert_eq!(core.memory.read_raw(Address::from_raw(PRODH_ADDR)), 0xFD);
    }

    // ---- arithmetic + FSR indirection ----

    #[test]
    fn addwf_postinc0_to_f_advances_fsr_exactly_once() {
        // ADDWF POSTINC0, F, ACCESS = 0x26EE.
        // FSR0=0x100, RAM[0x100]=0x10, W=0x05 → result = 0x15
        // written to RAM[0x100]; FSR0 advances to 0x101 EXACTLY ONCE.
        let mut core = k20_core_with_flash(&[0xEE, 0x26]);
        set_fsr0(&mut core, 0x100);
        core.memory.write_raw(Address::from_raw(0x100), 0x10);
        // Pre-load 0x101 with sentinel to detect double-advance.
        core.memory.write_raw(Address::from_raw(0x101), 0x99);
        write_w(&mut core, 0x05);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0x100)), 0x15);
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0x101)),
            0x99,
            "FSR advanced too far -- write hit the wrong slot"
        );
        assert_eq!(read_fsr0(&core), 0x101);
    }

    // ---- logical / rotate / swap ----

    #[test]
    fn andwf_w_and_f_to_w_clears_z_when_nonzero() {
        // ANDWF 0x10, W, ACCESS: high8 = 0x14, low = 0x10 → 0x1410.
        // W=0xF0, RAM[0x10]=0xCC → result = 0xC0.
        let mut core = k20_core_with_flash(&[0x10, 0x14]);
        write_w(&mut core, 0xF0);
        core.memory.write_raw(Address::from_raw(0x010), 0xCC);
        // Pre-set Z to confirm it gets cleared.
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), STATUS_Z);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_w(&core), 0xC0);
        assert!(read_status(&core) & STATUS_Z == 0);
        assert!(read_status(&core) & STATUS_N != 0, "0xC0 has bit 7 set");
    }

    #[test]
    fn iorwf_w_or_f_to_w_sets_n_for_negative_result() {
        // IORWF 0x10, W, ACCESS: high8 = 0x10, low = 0x10 → 0x1010.
        let mut core = k20_core_with_flash(&[0x10, 0x10]);
        write_w(&mut core, 0x80);
        core.memory.write_raw(Address::from_raw(0x010), 0x01);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_w(&core), 0x81);
        assert!(read_status(&core) & STATUS_N != 0);
    }

    #[test]
    fn xorwf_clears_to_zero_sets_z() {
        // XORWF 0x10, W, ACCESS: high8 = 0x18, low = 0x10 → 0x1810.
        // W ^ f with W = f → 0.
        let mut core = k20_core_with_flash(&[0x10, 0x18]);
        write_w(&mut core, 0x55);
        core.memory.write_raw(Address::from_raw(0x010), 0x55);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_w(&core), 0x00);
        assert!(read_status(&core) & STATUS_Z != 0);
    }

    #[test]
    fn comf_inverts_byte() {
        // COMF 0x10, W, ACCESS: high8 = 0x1C, low = 0x10 → 0x1C10.
        let mut core = k20_core_with_flash(&[0x10, 0x1C]);
        core.memory.write_raw(Address::from_raw(0x010), 0xAA);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_w(&core), 0x55);
    }

    #[test]
    fn rlcf_rotates_left_through_carry() {
        // RLCF 0x10, F, ACCESS: high8 = 0x36 (high6=001101, d=1, a=0), low = 0x10 → 0x3610.
        // f = 0x80, C_in = 1 → result = (0x80 << 1) | 1 = 0x01;
        // C_out = bit 7 of 0x80 = 1.
        let mut core = k20_core_with_flash(&[0x10, 0x36]);
        core.memory.write_raw(Address::from_raw(0x010), 0x80);
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), STATUS_C);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0x010)), 0x01);
        assert!(read_status(&core) & STATUS_C != 0);
        assert!(read_status(&core) & STATUS_Z == 0);
    }

    #[test]
    fn rrcf_rotates_right_through_carry() {
        // RRCF 0x10, F, ACCESS: high8 = 0x32, low = 0x10 → 0x3210.
        // f = 0x01, C_in = 0 → result = 0x00; C_out = bit 0 = 1.
        let mut core = k20_core_with_flash(&[0x10, 0x32]);
        core.memory.write_raw(Address::from_raw(0x010), 0x01);
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), 0);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0x010)), 0x00);
        assert!(read_status(&core) & STATUS_C != 0);
        assert!(read_status(&core) & STATUS_Z != 0);
    }

    #[test]
    fn rlncf_rotates_without_carry() {
        // RLNCF 0x10, F, ACCESS: high8 = 0x46, low = 0x10 → 0x4610.
        // f = 0x81 → 0x03 (bit 7 wraps to bit 0).
        let mut core = k20_core_with_flash(&[0x10, 0x46]);
        core.memory.write_raw(Address::from_raw(0x010), 0x81);
        // Pre-clear C; RLNCF must NOT touch C.
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), 0);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0x010)), 0x03);
        assert!(read_status(&core) & STATUS_C == 0, "RLNCF must not touch C");
    }

    #[test]
    fn rrncf_rotates_right_without_carry() {
        // RRNCF 0x10, F, ACCESS: high8 = 0x42, low = 0x10 → 0x4210.
        // f = 0x01 → 0x80 (bit 0 wraps to bit 7).  N=1 expected.
        let mut core = k20_core_with_flash(&[0x10, 0x42]);
        core.memory.write_raw(Address::from_raw(0x010), 0x01);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0x010)), 0x80);
        assert!(read_status(&core) & STATUS_N != 0);
    }

    #[test]
    fn swapf_swaps_nibbles_without_touching_status() {
        // SWAPF 0x10, F, ACCESS: high8 = 0x3A, low = 0x10 → 0x3A10.
        // f = 0xAB → 0xBA.
        let mut core = k20_core_with_flash(&[0x10, 0x3A]);
        core.memory.write_raw(Address::from_raw(0x010), 0xAB);
        // Pre-set every implemented STATUS bit; SWAPF must not
        // touch any of them.
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), STATUS_VALID_MASK);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0x010)), 0xBA);
        assert_eq!(read_status(&core), STATUS_VALID_MASK);
    }

    // ---- §5.3.6: arithmetic-to-STATUS preserves flag update ----

    #[test]
    fn addwf_to_status_preserves_flag_update() {
        // ADDWF STATUS, F, ACCESS: high8 = 0x26, low = 0xD8 → 0x26D8.
        // W=0x01, STATUS=0x00.  result = 0x01.  Flag update sets C=0
        // DC=0 Z=0 OV=0 N=0.  §5.3.6 says the result-write to
        // STATUS is dropped, so STATUS retains only the flag bits
        // -- the byte 0x01 should NOT land at 0xFD8.
        let mut core = k20_core_with_flash(&[0xD8, 0x26]);
        write_w(&mut core, 0x01);
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), 0);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        // STATUS should be all-zero (every flag cleared since 0+1=1
        // is non-zero, no carry, no overflow, positive).
        // If the write went through, STATUS would equal 0x01, which
        // happens to be just C set.
        let s = read_status(&core);
        assert_eq!(s, 0, "STATUS write must be dropped per §5.3.6");
    }

    // ------------------------------------------------------------
    // FSR indirect addressing -- INDF / POSTINC / POSTDEC /
    // PREINC / PLUSW.  Exercised through SETF / CLRF / MOVF /
    // MOVWF / MOVFF since those are the data-movement ops landed
    // so far.  Each test pins the FSR mutation contract per
    // DS39632E §5.5.4 + §5.5.5.
    // ------------------------------------------------------------

    /// Helper: load FSR0 with a 12-bit address by writing FSR0H + FSR0L.
    fn set_fsr0(core: &mut Core, value: u16) {
        core.memory.write_raw(Address::from_raw(0xFE9), value as u8);
        core.memory
            .write_raw(Address::from_raw(0xFEA), ((value >> 8) as u8) & 0x0F);
    }

    fn read_fsr0(core: &Core) -> u16 {
        let lo = core.memory.read_raw(Address::from_raw(0xFE9));
        let hi = core.memory.read_raw(Address::from_raw(0xFEA)) & 0x0F;
        ((hi as u16) << 8) | lo as u16
    }

    #[test]
    fn setf_indf0_writes_through_fsr0_pointer() {
        // SETF INDF0 = SETF 0xEF, ACCESS = 0x68EF.
        // FSR0 = 0x100 → write 0xFF to RAM[0x100]; FSR0
        // unchanged.
        let mut core = k20_core_with_flash(&[0xEF, 0x68]);
        set_fsr0(&mut core, 0x100);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0x100)), 0xFF);
        assert_eq!(read_fsr0(&core), 0x100, "INDF leaves FSR0 untouched");
    }

    #[test]
    fn clrf_postinc0_writes_zero_then_increments_fsr0() {
        // CLRF POSTINC0 = CLRF 0xEE, ACCESS = 0x6AEE.
        // FSR0 = 0x100 → clear RAM[0x100]; FSR0 ← 0x101.
        let mut core = k20_core_with_flash(&[0xEE, 0x6A]);
        set_fsr0(&mut core, 0x100);
        core.memory.write_raw(Address::from_raw(0x100), 0xAA);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0x100)), 0x00);
        assert_eq!(read_fsr0(&core), 0x101, "POSTINC mutates FSR0 by +1");
    }

    #[test]
    fn movf_postdec1_reads_then_decrements_fsr1() {
        // MOVF POSTDEC1, W, ACCESS = 0x50E5.
        // FSR1 = 0x200 → load W with RAM[0x200]; FSR1 ← 0x1FF.
        let mut core = k20_core_with_flash(&[0xE5, 0x50]);
        // Set FSR1 = 0x200.
        core.memory.write_raw(Address::from_raw(0xFE1), 0x00);
        core.memory.write_raw(Address::from_raw(0xFE2), 0x02);
        core.memory.write_raw(Address::from_raw(0x200), 0x42);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_w(&core), 0x42);
        // FSR1 = 0x1FF.
        let fsr1l = core.memory.read_raw(Address::from_raw(0xFE1));
        let fsr1h = core.memory.read_raw(Address::from_raw(0xFE2)) & 0x0F;
        assert_eq!(((fsr1h as u16) << 8) | fsr1l as u16, 0x1FF);
    }

    #[test]
    fn setf_preinc2_increments_fsr2_first_then_writes() {
        // SETF PREINC2 = SETF 0xDC, ACCESS = 0x68DC.
        // FSR2 = 0x300 → FSR2 ← 0x301, then RAM[0x301] = 0xFF.
        let mut core = k20_core_with_flash(&[0xDC, 0x68]);
        // Set FSR2 = 0x300.
        core.memory.write_raw(Address::from_raw(0xFD9), 0x00);
        core.memory.write_raw(Address::from_raw(0xFDA), 0x03);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        // RAM[0x300] still default (0); RAM[0x301] = 0xFF.
        assert_eq!(core.memory.read_raw(Address::from_raw(0x300)), 0x00);
        assert_eq!(core.memory.read_raw(Address::from_raw(0x301)), 0xFF);
        let fsr2l = core.memory.read_raw(Address::from_raw(0xFD9));
        let fsr2h = core.memory.read_raw(Address::from_raw(0xFDA)) & 0x0F;
        assert_eq!(((fsr2h as u16) << 8) | fsr2l as u16, 0x301);
    }

    #[test]
    fn movf_plusw0_uses_signed_w_offset_and_leaves_fsr0_alone() {
        // MOVF PLUSW0, W, ACCESS = 0x50EB.  FSR0 = 0x100,
        // W = 0x05 → load from RAM[0x105]; FSR0 untouched.
        let mut core = k20_core_with_flash(&[0xEB, 0x50]);
        set_fsr0(&mut core, 0x100);
        write_w(&mut core, 0x05);
        core.memory.write_raw(Address::from_raw(0x105), 0xCC);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_w(&core), 0xCC, "loaded byte from FSR0+W");
        assert_eq!(read_fsr0(&core), 0x100, "PLUSW leaves FSR0 untouched");
    }

    #[test]
    fn movf_plusw0_with_negative_w_subtracts() {
        // W = 0xFF (= -1 signed); FSR0 = 0x100 → target 0x0FF.
        let mut core = k20_core_with_flash(&[0xEB, 0x50]);
        set_fsr0(&mut core, 0x100);
        write_w(&mut core, 0xFF);
        core.memory.write_raw(Address::from_raw(0x0FF), 0x77);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_w(&core), 0x77);
    }

    #[test]
    fn movff_with_postinc_src_and_postinc_dst_mutates_both_fsrs() {
        // MOVFF POSTINC0, POSTINC1: word1 = 0xC___ src=0xFEE
        //   = 1100_1111_1110_1110 = 0xCFEE
        // word2 = 0xF___ dst=0xFE6 = 0xFFE6.
        let mut core = k20_core_with_flash(&[0xEE, 0xCF, 0xE6, 0xFF]);
        set_fsr0(&mut core, 0x100);
        // Set FSR1 = 0x200.
        core.memory.write_raw(Address::from_raw(0xFE1), 0x00);
        core.memory.write_raw(Address::from_raw(0xFE2), 0x02);
        core.memory.write_raw(Address::from_raw(0x100), 0x99);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        // src copied to dst.
        assert_eq!(core.memory.read_raw(Address::from_raw(0x200)), 0x99);
        // Both FSRs incremented.
        assert_eq!(read_fsr0(&core), 0x101);
        let fsr1l = core.memory.read_raw(Address::from_raw(0xFE1));
        let fsr1h = core.memory.read_raw(Address::from_raw(0xFE2)) & 0x0F;
        assert_eq!(((fsr1h as u16) << 8) | fsr1l as u16, 0x201);
    }

    #[test]
    fn movf_preinc0_to_w_reads_through_post_increment_fsr_self_reference() {
        // Self-referential PREINC corner case: FSR0 = 0xFE8
        // (one below FSR0L's address).  PREINC0 must
        // pre-increment FSR0 to 0xFE9, then read *0xFE9 -- which
        // IS FSR0L itself.  Per silicon (DS39632E §5.5.4), the
        // FSR mutation happens BEFORE the access, so the read
        // observes the new low byte (0xE9), NOT the old (0xE8).
        //
        // Without the inline pre-commit, deferred-commit
        // semantics would read RAM[0xFE9] = FSR0L = 0xE8 (the
        // pre-update value), then commit -- W ends up wrong.
        //
        // MOVF PREINC0, W, ACCESS = 0x50EC.
        let mut core = k20_core_with_flash(&[0xEC, 0x50]);
        // FSR0 = 0xFE8.
        core.memory.write_raw(Address::from_raw(0xFE9), 0xE8);
        core.memory.write_raw(Address::from_raw(0xFEA), 0x0F);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        // FSR0 advanced to 0xFE9.
        assert_eq!(read_fsr0(&core), 0xFE9);
        // W must hold the *post-increment* FSR0L byte (0xE9).
        assert_eq!(read_w(&core), 0xE9);
    }

    #[test]
    fn movf_postinc0_to_f_advances_fsr_exactly_once() {
        // RMW regression: `MOVF POSTINC0, F` is the firmware
        // idiom "test the byte at *FSR0, then advance FSR0".
        // Per gpsim's fsr_state model + DS39632E §5.5.4, the
        // post-increment must happen ONCE per instruction --
        // not once on read AND once on write.  Naively chaining
        // read_f + write_addr would advance FSR0 by 2 and write
        // the byte to the wrong slot.
        //
        // MOVF POSTINC0, F, ACCESS:
        //   bit 9 = d (1 for F), bit 8 = a (0 for ACCESS)
        //   high6 = 0101 00 = 0x14 → high8 = 0x52
        //   word1 = 0x52EE.
        let mut core = k20_core_with_flash(&[0xEE, 0x52]);
        set_fsr0(&mut core, 0x100);
        core.memory.write_raw(Address::from_raw(0x100), 0x42);
        // 0x101 stays default (0); if FSR advances twice, the
        // byte at 0x100 will be unchanged but 0x101 will get
        // overwritten with 0x42 -- pin both to catch either.
        core.memory.write_raw(Address::from_raw(0x101), 0x99);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();

        // Byte at 0x100 was 0x42 → MOVF f, F writes it back to
        // 0x100 (the original target).  0x101 must NOT have
        // been touched.
        assert_eq!(core.memory.read_raw(Address::from_raw(0x100)), 0x42);
        assert_eq!(
            core.memory.read_raw(Address::from_raw(0x101)),
            0x99,
            "FSR advanced too far (2 instead of 1) and write hit the wrong slot"
        );
        // FSR0 must end at exactly 0x101 (advanced by 1).
        assert_eq!(read_fsr0(&core), 0x101);
        // And Z=0 / N=0 since the byte was 0x42 (non-zero, bit 7 clear).
        assert!(read_status(&core) & STATUS_Z == 0);
        assert!(read_status(&core) & STATUS_N == 0);
    }

    #[test]
    fn fsr_pointer_wraps_modulo_4096_on_increment_past_end() {
        // FSR2 = 0xFFF, POSTINC2 → use 0xFFF, then FSR2 ← 0x000
        // (12-bit wrap).
        // SETF POSTINC2 = SETF 0xDE, ACCESS = 0x68DE.
        let mut core = k20_core_with_flash(&[0xDE, 0x68]);
        core.memory.write_raw(Address::from_raw(0xFD9), 0xFF);
        core.memory.write_raw(Address::from_raw(0xFDA), 0x0F);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        let fsr2l = core.memory.read_raw(Address::from_raw(0xFD9));
        let fsr2h = core.memory.read_raw(Address::from_raw(0xFDA)) & 0x0F;
        assert_eq!(((fsr2h as u16) << 8) | fsr2l as u16, 0x000);
    }

    #[test]
    fn movlb_writes_low_4_bits_of_bsr() {
        // MOVLB 0x05 — opcode 0x0105 (per decoder; high8=0x01).
        let mut core = k20_core_with_flash(&[0x05, 0x01]);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_bsr(&core), 0x05);
    }

    #[test]
    fn movf_status_to_status_preserves_flag_update() {
        // DS39632E §5.3.6: when STATUS is the destination of a
        // flag-affecting instruction, the result write is
        // dropped; only the flag update lands.  `MOVF STATUS, F`
        // with STATUS initially 0 must end with Z set, NOT with
        // STATUS still equal to its original 0.
        //
        // STATUS in access-bank low: f = STATUS_ADDR & 0xFF = 0xD8.
        // MOVF 0xD8, F, ACCESS = 0x52D8.
        let mut core = k20_core_with_flash(&[0xD8, 0x52]);
        // Pre-clear STATUS.
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), 0);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        // Without the fix: STATUS would be re-written as 0,
        // clobbering the Z-set step.  With the fix: Z stays set.
        assert!(read_status(&core) & STATUS_Z != 0, "Z must survive");
    }

    #[test]
    fn movf_status_to_w_loads_status_byte_normally() {
        // When d=W, the result write goes to W (not STATUS), so
        // the flag update + the W load both happen.
        let mut core = k20_core_with_flash(&[0xD8, 0x50]); // MOVF 0xD8, W, ACCESS
        core.memory.write_raw(Address::from_raw(STATUS_ADDR), STATUS_C); // C set
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        // W picks up the original STATUS byte (only C set).
        assert_eq!(read_w(&core), STATUS_C);
        // STATUS gets Z/N updated based on the loaded byte (0x01):
        // not zero, bit 7 clear → Z=0, N=0.  C bit was already
        // set on entry; Z/N updates leave C alone.
        assert!(read_status(&core) & STATUS_Z == 0);
        assert!(read_status(&core) & STATUS_N == 0);
        assert!(read_status(&core) & STATUS_C != 0, "C must remain set");
    }

    #[test]
    fn movwf_to_status_strips_unimplemented_bits() {
        // STATUS<7:5> are unimplemented (read as 0 on real
        // silicon).  A MOVWF STATUS attempt with W=0xFF must
        // store only STATUS_VALID_MASK = 0x1F.
        // MOVLW 0xFF = 0x0EFF; MOVWF 0xD8, ACCESS = 0x6ED8.
        let mut core = k20_core_with_flash(&[0xFF, 0x0E, 0xD8, 0x6E]);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap(); // MOVLW
        step(&mut core, &mut stack).unwrap(); // MOVWF
        assert_eq!(
            read_status(&core),
            STATUS_VALID_MASK,
            "STATUS<7:5> must read as 0 even after a 0xFF write"
        );
    }

    #[test]
    fn movwf_to_bsr_strips_unimplemented_bits() {
        // BSR<7:4> are unimplemented.  MOVWF BSR with W=0xF7
        // must store only the low nibble.
        // MOVLW 0xF7 = 0x0EF7; MOVWF 0xE0, ACCESS = 0x6EE0.
        let mut core = k20_core_with_flash(&[0xF7, 0x0E, 0xE0, 0x6E]);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_bsr(&core), 0x07);
    }

    #[test]
    fn movwf_to_intcon2_strips_unimplemented_bits() {
        // INTCON2<3,1> unimplemented (Register 9-2).  MOVWF
        // INTCON2 with W=0xFF must store 0xF5.
        // MOVLW 0xFF = 0x0EFF; MOVWF 0xF1, ACCESS = 0x6EF1.
        let mut core = k20_core_with_flash(&[0xFF, 0x0E, 0xF1, 0x6E]);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFF1)), 0xF5);
    }

    #[test]
    fn movwf_to_eecon1_strips_unimplemented_bit_5() {
        // EECON1<5> unimplemented (Register 6-1).  EECON1 is
        // at 0xFA6 (gputils p18f2455.inc); 0xA6 is in the
        // Access-Bank high half so a=ACCESS routes there.
        // MOVLW 0xFF = 0x0EFF; MOVWF 0xA6, ACCESS = 0x6EA6.
        let mut core = k20_core_with_flash(&[0xFF, 0x0E, 0xA6, 0x6E]);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFA6)), 0xDF);
    }

    #[test]
    fn movwf_to_eecon2_zeroes_storage() {
        // EECON2 is not a physical register; reads return 0
        // (DS39632E §6.2.1).  Mask writes to 0x00 so a later
        // raw read (or MOVF) returns the silicon-correct 0,
        // not whatever the firmware wrote.
        // EECON2 at 0xFA7; f=0xA7 routes via Access-Bank high.
        // MOVLW 0xFF = 0x0EFF; MOVWF 0xA7, ACCESS = 0x6EA7.
        let mut core = k20_core_with_flash(&[0xFF, 0x0E, 0xA7, 0x6E]);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFA7)), 0x00);
    }

    #[test]
    fn movwf_to_intcon3_strips_unimplemented_bits() {
        // INTCON3<5,2> unimplemented (Register 9-3).
        // MOVWF 0xF0, ACCESS = 0x6EF0.
        let mut core = k20_core_with_flash(&[0xFF, 0x0E, 0xF0, 0x6E]);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFF0)), 0xDB);
    }

    #[test]
    fn movwf_to_fsr0h_strips_high_nibble() {
        // FSR0H<7:4> unimplemented (12-bit FSR; only <3:0>
        // alive).  MOVWF FSR0H with W=0xCB must store only
        // 0x0B.  This is the most user-visible case of the
        // sfr_write_mask extension -- firmware sets up indirect
        // pointers via MOVWF FSR0H and read-back must match
        // silicon's 0-read-for-unimplemented contract.
        // MOVLW 0xCB = 0x0ECB; MOVWF 0xEA, ACCESS = 0x6EEA.
        let mut core = k20_core_with_flash(&[0xCB, 0x0E, 0xEA, 0x6E]);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(core.memory.read_raw(Address::from_raw(0xFEA)), 0x0B);
    }

    #[test]
    fn movlb_truncates_literal_to_4_bits() {
        // PIC18 BSR is 4 bits; MOVLB stores the low nibble only.
        // The decoder pulls only the low 4 bits of the literal
        // from word1 (`word1 & 0x0F`), so an attempt to encode
        // `MOVLB 0xFA` actually decodes as MOVLB 0x0A.  The
        // executor's BSR write also masks to 4 bits as a
        // belt-and-suspenders guard.  Pin both layers by
        // pre-setting BSR to 0xFF (raw) and confirming the high
        // nibble gets cleared after MOVLB.
        // Build opcode by hand: word1 = 0x010A → MOVLB 0x0A.
        let mut core = k20_core_with_flash(&[0x0A, 0x01]);
        // Stash garbage in the BSR high nibble by writing raw.
        core.memory.write_raw(Address::from_raw(BSR_ADDR), 0xF7);
        let mut stack = Stack::new();
        step(&mut core, &mut stack).unwrap();
        assert_eq!(read_bsr(&core), 0x0A);
    }
}
