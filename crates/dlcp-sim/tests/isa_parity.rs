//! Phase-1 ISA-parity integration tests
//! (`docs/SIM_REWRITE_RUST_SPEC.md` §5).
//!
//! P1.8c lays the file down with the
//! `isa_covers_all_75_pic18_opcodes` fuzzer-style coverage
//! gate: every documented PIC18 opcode is dispatched by
//! `Core::step` at least once across this test program.
//! P1.8d / P1.8e extend the same file with the gpsim
//! ground-truth parity tests against V1.71 / V3.2 boots.

use dlcp_sim::{Core, Instruction, Stack, TableMode, Variant, decode, step};
use std::collections::HashMap;
use std::mem::Discriminant;

/// Coverage tag.  Most PIC18 instructions are uniquely
/// identified by their `Instruction` enum variant; the two
/// table ops (`TblRd`, `TblWt`) carry a `mode` field that
/// fans out to four documented mnemonics each, so we tag
/// them on (variant, mode) instead.
#[derive(Eq, PartialEq, Hash, Copy, Clone, Debug)]
enum CoverageTag {
    Variant(Discriminant<Instruction>),
    TblRd(TableMode),
    TblWt(TableMode),
}

fn tag_for(instr: &Instruction) -> CoverageTag {
    match instr {
        Instruction::TblRd { mode } => CoverageTag::TblRd(*mode),
        Instruction::TblWt { mode } => CoverageTag::TblWt(*mode),
        other => CoverageTag::Variant(std::mem::discriminant(other)),
    }
}

/// 75 documented PIC18 opcodes per DS39632E §26.  Each entry
/// is `(bytes, mnemonic)` -- the bytes form a complete
/// little-endian instruction (2 bytes for single-word ops,
/// 4 bytes for the four 2-word ops MOVFF / CALL / LFSR /
/// GOTO).  Encodings are spot-checked against
/// `crates/dlcp-sim/src/isa/decode.rs` and gputils' p18f2455
/// inc when needed.
const OPCODES: &[(&[u8], &str)] = &[
    // ----- byte-oriented (31) -----
    (&[0x10, 0x24], "ADDWF"),
    (&[0x10, 0x20], "ADDWFC"),
    (&[0x10, 0x14], "ANDWF"),
    (&[0x10, 0x6A], "CLRF"),
    (&[0x10, 0x1C], "COMF"),
    (&[0x10, 0x62], "CPFSEQ"),
    (&[0x10, 0x64], "CPFSGT"),
    (&[0x10, 0x60], "CPFSLT"),
    (&[0x10, 0x06], "DECF"),
    (&[0x10, 0x2E], "DECFSZ"),
    (&[0x10, 0x4E], "DCFSNZ"),
    (&[0x10, 0x2A], "INCF"),
    (&[0x10, 0x3E], "INCFSZ"),
    (&[0x10, 0x4A], "INFSNZ"),
    (&[0x10, 0x10], "IORWF"),
    (&[0x10, 0x50], "MOVF"),
    (&[0x10, 0xC1, 0x20, 0xF1], "MOVFF"),
    (&[0x10, 0x6E], "MOVWF"),
    (&[0x10, 0x02], "MULWF"),
    (&[0x10, 0x6C], "NEGF"),
    (&[0x10, 0x36], "RLCF"),
    (&[0x10, 0x46], "RLNCF"),
    (&[0x10, 0x32], "RRCF"),
    (&[0x10, 0x42], "RRNCF"),
    (&[0x10, 0x68], "SETF"),
    (&[0x10, 0x54], "SUBFWB"),
    (&[0x10, 0x5C], "SUBWF"),
    (&[0x10, 0x58], "SUBWFB"),
    (&[0x10, 0x3A], "SWAPF"),
    (&[0x10, 0x66], "TSTFSZ"),
    (&[0x10, 0x18], "XORWF"),
    // ----- bit-oriented (5) -----
    (&[0x10, 0x90], "BCF"),
    (&[0x10, 0x80], "BSF"),
    (&[0x10, 0xB0], "BTFSC"),
    (&[0x10, 0xA0], "BTFSS"),
    (&[0x10, 0x70], "BTG"),
    // ----- literal (10) -----
    (&[0x42, 0x0F], "ADDLW"),
    (&[0x42, 0x0B], "ANDLW"),
    (&[0x42, 0x09], "IORLW"),
    (&[0x00, 0xEE, 0x00, 0xF0], "LFSR"),
    (&[0x05, 0x01], "MOVLB"),
    (&[0x42, 0x0E], "MOVLW"),
    (&[0x42, 0x0D], "MULLW"),
    (&[0x42, 0x0C], "RETLW"),
    (&[0x42, 0x08], "SUBLW"),
    (&[0x42, 0x0A], "XORLW"),
    // ----- control (21) -----
    (&[0x05, 0xE2], "BC"),
    (&[0x05, 0xE6], "BN"),
    (&[0x05, 0xE3], "BNC"),
    (&[0x05, 0xE7], "BNN"),
    (&[0x05, 0xE5], "BNOV"),
    (&[0x05, 0xE1], "BNZ"),
    (&[0x05, 0xE4], "BOV"),
    (&[0x05, 0xD0], "BRA"),
    (&[0x05, 0xE0], "BZ"),
    (&[0x40, 0xEC, 0x00, 0xF0], "CALL"),
    (&[0x04, 0x00], "CLRWDT"),
    (&[0x07, 0x00], "DAW"),
    (&[0x10, 0xEF, 0x00, 0xF0], "GOTO"),
    (&[0x00, 0x00], "NOP"),
    (&[0x06, 0x00], "POP"),
    (&[0x05, 0x00], "PUSH"),
    (&[0x05, 0xD8], "RCALL"),
    (&[0xFF, 0x00], "RESET"),
    (&[0x10, 0x00], "RETFIE"),
    (&[0x12, 0x00], "RETURN"),
    (&[0x03, 0x00], "SLEEP"),
    // ----- table (8) -----
    (&[0x08, 0x00], "TBLRD*"),
    (&[0x09, 0x00], "TBLRD*+"),
    (&[0x0A, 0x00], "TBLRD*-"),
    (&[0x0B, 0x00], "TBLRD+*"),
    (&[0x0C, 0x00], "TBLWT*"),
    (&[0x0D, 0x00], "TBLWT*+"),
    (&[0x0E, 0x00], "TBLWT*-"),
    (&[0x0F, 0x00], "TBLWT+*"),
];

/// Phase-1 verification gate per spec §5.  Walks each of the
/// 75 documented PIC18 opcodes through `Core::step` on a
/// fresh Core+Stack, decodes the instruction in parallel for
/// the coverage tag, and asserts:
///
///   - every invocation succeeds (no `ExecError`);
///   - every coverage tag is unique (no two byte patterns
///     decode to the same variant -- catches table-encoding
///     drift); and
///   - the final tag set has exactly 75 entries (the full
///     PIC18 ISA per DS39632E §26).
#[test]
fn isa_covers_all_75_pic18_opcodes() {
    let mut covered: HashMap<CoverageTag, &str> = HashMap::new();

    for (bytes, mnemonic) in OPCODES {
        // Spawn a fresh core + stack for every opcode so
        // cross-test pollution (PC moves, stack push/pop, FSR
        // mutations) doesn't matter.  K20 variant is fine for
        // both 2455 and K20 -- the ISA is byte-for-byte
        // identical (the only difference is which SFRs are
        // alive).
        let mut core = Core::new(Variant::Pic18F25K20);
        let len = bytes.len();
        core.flash_mut()[..len].copy_from_slice(bytes);

        let mut stack = Stack::new();
        let result = step(&mut core, &mut stack);
        assert!(
            result.is_ok(),
            "{mnemonic} ({bytes:02X?}) failed to dispatch: {result:?}"
        );

        // Decode in parallel to derive the coverage tag.
        // step() doesn't return the Instruction itself, but
        // re-decoding from the same bytes is deterministic.
        let word1 = u16::from_le_bytes([bytes[0], bytes[1]]);
        let word2 = if len >= 4 {
            u16::from_le_bytes([bytes[2], bytes[3]])
        } else {
            0xFFFF
        };
        let (instr, _) = decode(word1, word2);
        let tag = tag_for(&instr);

        // Coverage map invariant: every mnemonic produces a
        // unique tag.  A duplicate tag means two byte
        // patterns in OPCODES decode to the same variant --
        // a table maintenance error.
        if let Some(prev) = covered.insert(tag, mnemonic) {
            panic!(
                "duplicate coverage tag: {mnemonic} ({bytes:02X?}) decodes to the same variant as {prev}"
            );
        }
    }

    assert_eq!(
        covered.len(),
        75,
        "expected coverage of 75 documented PIC18 opcodes; got {} -- did the table miss one?",
        covered.len()
    );
}
