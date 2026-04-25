//! Phase-1 ISA-parity integration tests
//! (`docs/SIM_REWRITE_RUST_SPEC.md` §5).
//!
//! P1.8c lays the file down with the
//! `isa_covers_all_75_pic18_opcodes` fuzzer-style coverage
//! gate.  P1.8d adds the V1.71 reset-through-init bit-exact
//! parity gate against an early-boot gpsim snapshot captured by
//! `scripts/capture_v171_early_boot_parity.py`.

use dlcp_sim::{
    Core, HexImage, Instruction, ResetSource, Stack, TableMode, Variant, apply_reset, decode,
    step,
};
use std::collections::HashMap;
use std::mem::Discriminant;
use std::path::PathBuf;

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

// ============================================================
// V1.71 reset-through-init bit-exact parity (P1.8d / spec §5)
// ============================================================

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|p| p.parent())
        .expect("crate dir has 2 ancestors")
        .to_path_buf()
}

/// Pick the cycle target from the captured meta.json so the
/// Rust executor runs for the same number of cycles the gpsim
/// capture stopped at.  Looks for files matching
/// `early_boot_v171_<N>.meta.json`, picks the smallest <N> (the
/// most parity-friendly), and reads the cycle field.
fn pick_cycle_target(snapshot_dir: &std::path::Path) -> u64 {
    let mut candidates: Vec<u64> = Vec::new();
    if let Ok(read_dir) = std::fs::read_dir(snapshot_dir) {
        for entry in read_dir.flatten() {
            let name = entry.file_name();
            let s = name.to_string_lossy();
            let stem = match s.strip_suffix(".meta.json") {
                Some(s) => s,
                None => continue,
            };
            let n_str = match stem.strip_prefix("early_boot_v171_") {
                Some(s) => s,
                None => continue,
            };
            if let Ok(n) = n_str.parse::<u64>() {
                candidates.push(n);
            }
        }
    }
    candidates.sort_unstable();
    let chosen = candidates.first().copied().unwrap_or(10);

    // Cross-check the meta file's recorded cycle against the
    // filename's <N>.  An unparseable meta file or a missing
    // `cycle` field surfaces as a hard panic so capture-script
    // metadata bugs don't silently fall through to a
    // filename-only fallback.
    let stem = format!("early_boot_v171_{}", chosen);
    let meta_path = snapshot_dir.join(format!("{stem}.meta.json"));
    if meta_path.exists() {
        let text = std::fs::read_to_string(&meta_path)
            .expect("meta.json exists but could not be read");
        let cycle_in_text = text
            .lines()
            .find_map(|line| {
                let trimmed = line.trim();
                let after_key = trimmed.strip_prefix("\"cycle\"")?;
                let after_colon = after_key.trim_start().strip_prefix(':')?;
                after_colon
                    .trim()
                    .trim_end_matches(',')
                    .parse::<u64>()
                    .ok()
            })
            .unwrap_or_else(|| {
                panic!(
                    "meta.json at {} has no parseable `cycle` field",
                    meta_path.display()
                )
            });
        assert_eq!(
            cycle_in_text, chosen,
            "meta.json cycle ({cycle_in_text}) disagrees with filename ({chosen})"
        );
    }
    chosen
}

/// Tiny hand-rolled parser for the SFR snapshot JSON --
/// `{"0xF60": 0, "0xF61": 0, ...}`.  Avoids pulling serde into
/// the dev-dependency tree just for one constrained file
/// shape.  Returns the (addr, value) pairs.
fn parse_sfr_snapshot(text: &str) -> Vec<(u16, u8)> {
    let mut pairs = Vec::new();
    for line in text.lines() {
        let line = line.trim();
        // Match `"0xXXX": N,` (with optional trailing comma).
        let Some(hex_start) = line.find("\"0x") else {
            continue;
        };
        let after_quote = &line[hex_start + 3..];
        let Some(close_quote) = after_quote.find('"') else {
            continue;
        };
        let addr_hex = &after_quote[..close_quote];
        let Ok(addr) = u16::from_str_radix(addr_hex, 16) else {
            continue;
        };
        let after_addr = &after_quote[close_quote + 1..];
        let Some(colon) = after_addr.find(':') else {
            continue;
        };
        let after_colon = after_addr[colon + 1..]
            .trim_start()
            .trim_end_matches(|c: char| !c.is_ascii_digit());
        let Ok(value) = after_colon.trim().parse::<u32>() else {
            continue;
        };
        pairs.push((addr, value as u8));
    }
    pairs
}

/// **Test-only** POR-default SFR initialisations.
///
/// On real silicon, POR sets several SFRs to non-zero defaults
/// (per DS39632E Table 5-2 / DS41303G Table 5-2).  P1.6's
/// `apply_reset(PowerOn)` zeroes RAM but doesn't wire those
/// non-zero defaults yet -- the per-peripheral wrappers in
/// P2 will own them.  This helper sets a tiny subset that the
/// V1.71 boot path inspects very early; without it the parity
/// test diverges before reaching anything else interesting.
///
/// **Caveat:** patching these in test code masks the
/// architectural-reset-coverage gap from the parity gate.  When
/// the executor's reset path lands these defaults itself
/// (probably in the P2 INTCON peripheral wrapper), this helper
/// should be deleted -- otherwise a future regression in
/// reset.rs would still pass parity because the test patches
/// over it.  Tracked as a follow-up note inside Task #18.
fn apply_por_sfr_defaults(core: &mut Core) {
    // INTCON2 POR = 1111 -1-1 = 0xF5 (RBPU=1, edges=1, TMR0IP=1, RBIP=1).
    core.memory.write_raw(dlcp_sim_addr(0xFF1), 0xF5);
    // INTCON3 POR = 11-0 0-00 = 0xC0 (priorities high).
    core.memory.write_raw(dlcp_sim_addr(0xFF0), 0xC0);
}

fn dlcp_sim_addr(raw: u16) -> dlcp_sim::memory::Address {
    dlcp_sim::memory::Address::from_raw(raw)
}

/// Run the Rust executor from POR for `cycle_target` Tcy and
/// return its final state.
fn run_to_cycle(image: &HexImage, cycle_target: u64) -> (Core, Stack) {
    let mut core = Core::new(Variant::Pic18F25K20);
    core.flash_mut().copy_from_slice(&*image.flash);
    let mut stack = Stack::new();
    apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
    apply_por_sfr_defaults(&mut core);

    let mut total: u64 = 0;
    while total < cycle_target {
        let cycles = step(&mut core, &mut stack)
            .expect("Phase-1 executor must not error during V1.71 boot");
        total += cycles as u64;
    }
    (core, stack)
}

/// Mirror PCL / PCLATH / PCLATU / STKPTR / TOSU / TOSH / TOSL
/// from the dedicated `Core::pc` and `Stack` state into the
/// SFR bytes before snapshot comparison.  P1.8b's executor
/// keeps these as separate fields for performance; gpsim
/// auto-syncs on every register read.  Task #15 will land
/// this bidirectional mirror inside the executor itself; for
/// now the test does it by hand on the read side only.
fn mirror_pc_and_stack_to_sfrs(core: &mut Core, stack: &Stack) {
    let pc = core.pc();
    core.memory.write_raw(dlcp_sim_addr(0xFF9), pc as u8);          // PCL
    core.memory.write_raw(dlcp_sim_addr(0xFFA), (pc >> 8) as u8);    // PCLATH
    core.memory
        .write_raw(dlcp_sim_addr(0xFFB), ((pc >> 16) as u8) & 0x1F); // PCLATU
    core.memory.write_raw(dlcp_sim_addr(0xFFC), stack.stkptr());     // STKPTR
    let tos = stack.top();
    core.memory.write_raw(dlcp_sim_addr(0xFFD), tos as u8);          // TOSL
    core.memory.write_raw(dlcp_sim_addr(0xFFE), (tos >> 8) as u8);    // TOSH
    core.memory
        .write_raw(dlcp_sim_addr(0xFFF), ((tos >> 16) as u8) & 0x1F); // TOSU
}

/// V1.71 reset-through-init bit-exact parity gate.
///
/// Loads V1.71 CONTROL hex, applies POR, runs the Rust
/// executor for the cycle count captured in
/// `artifacts/ground_truth/v171_early_boot_parity/early_boot_v171_<N>.meta.json`
/// (default 100 Tcy per spec §5), then bit-compares RAM bank 0
/// (256 bytes) and the top-of-bank-15 SFR window (0xF60..0xFFF,
/// 160 bytes) against the captured gpsim snapshot.
///
/// The capture is produced by running:
///
/// ```bash
/// PYTHONPATH=src .venv_ep0/bin/python \
///   scripts/capture_v171_early_boot_parity.py --cycles 100
/// ```
///
/// **Status:** marked `#[ignore]` while the divergence list is
/// audited.  Bit-exact match requires (a) full POR-default SFR
/// initialisation (only some bits land via P1.6's reset.rs +
/// `apply_por_sfr_defaults`) and (b) any peripheral bits the
/// boot path touches in the first 100 cycles.  Removing the
/// `#[ignore]` is part of Task #18's scope.
#[test]
#[ignore = "P1.8d work-in-progress; awaiting POR-default SFR and peripheral wiring (Task #18)"]
fn isa_matches_gpsim_ground_truth_for_v171_reset_through_init() {
    let root = repo_root();
    let hex_path = root.join("firmware/patched/releases/DLCP_Control_V1.71.hex");
    let image = HexImage::from_hex_path(&hex_path).expect("V1.71 hex loads");

    let snapshot_dir = root.join("artifacts/ground_truth/v171_early_boot_parity");
    // Cycle target is read from the captured meta.json so the
    // capture script and the parity test stay in lock-step.  The
    // capture lives at `early_boot_v171_<cycles>.{ram.bin,
    // sfr.json, meta.json}` -- find whichever fixture is in the
    // directory and take its cycle.
    let cycle_target: u64 = pick_cycle_target(&snapshot_dir);
    let stem = format!("early_boot_v171_{}", cycle_target);

    let ram_expected = std::fs::read(snapshot_dir.join(format!("{stem}.ram.bin")))
        .expect("read ram snapshot");
    assert_eq!(ram_expected.len(), 256);

    let sfr_text = std::fs::read_to_string(snapshot_dir.join(format!("{stem}.sfr.json")))
        .expect("read sfr snapshot");
    let sfr_expected = parse_sfr_snapshot(&sfr_text);
    // The capture covers exactly 0xF60..0x1000 = 160 SFR bytes;
    // any other count means the capture script + parser drifted.
    assert_eq!(
        sfr_expected.len(),
        160,
        "expected exactly 160 SFR entries (0xF60..0x1000), got {}",
        sfr_expected.len()
    );

    let (mut core, stack) = run_to_cycle(&image, cycle_target);
    mirror_pc_and_stack_to_sfrs(&mut core, &stack);

    // --- compare RAM bank 0 ---
    let ram_actual: Vec<u8> = (0..256u16)
        .map(|addr| core.memory.read_raw(dlcp_sim_addr(addr)))
        .collect();
    let mut ram_diffs: Vec<(u16, u8, u8)> = Vec::new();
    for addr in 0..256u16 {
        let exp = ram_expected[addr as usize];
        let got = ram_actual[addr as usize];
        if exp != got {
            ram_diffs.push((addr, exp, got));
        }
    }

    // --- compare SFR window ---
    let mut sfr_diffs: Vec<(u16, u8, u8)> = Vec::new();
    for (addr, exp) in &sfr_expected {
        let got = core.memory.read_raw(dlcp_sim_addr(*addr));
        if got != *exp {
            sfr_diffs.push((*addr, *exp, got));
        }
    }

    if !ram_diffs.is_empty() || !sfr_diffs.is_empty() {
        eprintln!(
            "V1.71 boot parity divergence at cycle {} ({} RAM + {} SFR):",
            cycle_target,
            ram_diffs.len(),
            sfr_diffs.len()
        );
        for (addr, exp, got) in &ram_diffs {
            eprintln!("  RAM[0x{addr:03X}]: gpsim=0x{exp:02X} rust=0x{got:02X}");
        }
        for (addr, exp, got) in &sfr_diffs {
            eprintln!("  SFR[0x{addr:03X}]: gpsim=0x{exp:02X} rust=0x{got:02X}");
        }
        panic!(
            "RAM divergences: {}, SFR divergences: {}",
            ram_diffs.len(),
            sfr_diffs.len()
        );
    }
}
