//! cargo-fuzz target: `ir_stream` — coverage-guided fuzzing of
//! `dlcp_sim::chain::Chain` driven by libfuzzer-mutated byte
//! streams interpreted as IR-style stimulus events.
//!
//! Spec ref: `docs/SIM_REWRITE_RUST_SPEC.md` §9 P5b.1 (stretch).
//!
//! Why a fuzz target on top of P5.4's deterministic 10⁴-scenario
//! soak?  The soak gives breadth over a *known* stimulus
//! distribution (xorshift seed corpus).  libFuzzer's value-add
//! is coverage-guided mutation: it discovers stimulus orderings
//! the soak's RNG never hits — e.g. very long blackout windows
//! between micro-steps, repeated scheduler-wake patterns,
//! near-saturation tick counts — by tracking branch coverage in
//! the simulator's hot paths.
//!
//! ## Input grammar
//!
//! libFuzzer hands us an opaque `&[u8]`.  The fuzzer runs many
//! iterations per second, so the per-iteration cost matters.  We
//! decode the byte stream as follows (all little-endian where
//! relevant):
//!
//!   * **Byte 0** — boot-offset seed.  Used to perturb the
//!     V1.71 chain's initial schedule via
//!     `Chain::schedule_initial_steps(&[byte0 as u64])`.
//!     Range 0..=255 ticks is enough to cross several event
//!     boundaries without dominating the iteration budget.
//!   * **Byte 1** — stimulus-count `n`, *saturating* at 8 (so
//!     the iteration finishes in a few hundred microseconds).
//!     Saturating, not modulo: byte values 9..=255 all decode
//!     as 8 stimuli.  (Codex LOW from b3d42a8: prior
//!     implementation used `byte % 9` which mapped byte 9 to
//!     0 stimuli, contradicting the "capped at 8" docs.)
//!   * **Bytes 2..2+n*5** — packed stimulus records.  Each
//!     record is 5 bytes:
//!       * byte[0]: stimulus tag.  0=StepTicks,
//!         1=SetUartBlackout, 2=InjectUartRxByte
//!         (the IR-command-style byte stream stimulus codex
//!         flagged the prior commit was missing -- the byte
//!         lands on V1.71 CONTROL's silicon EUSART RX FIFO
//!         via `Chain::inject_uart_rx_byte`).
//!         Other tag values: skip the record.
//!       * bytes[1..5]: u32 LE payload — interpreted as
//!         `step_ticks` clamped to ≤ 200_000 for `StepTicks`,
//!         `(payload & 1) == 1` for `SetUartBlackout`,
//!         `(payload & 0xFF) as u8` for `InjectUartRxByte`.
//!
//! Truncated input is OK; we stop decoding when fewer than 5
//! bytes remain.  An empty `data` means "no stimuli" and the
//! fuzz iteration just asserts snapshot determinism on the
//! freshly-built V1.71 chain.
//!
//! ## Per-iteration assertions
//!
//! For each fuzz iteration we assert TWO invariants on the
//! resulting Chain state:
//!
//!   1. `encode(decode(encode(c))?)? == encode(c)` — snapshot
//!      round-trip is byte-stable.
//!   2. Two chains given the same stimulus stream produce
//!      identical bytes (replay determinism).
//!
//! A failure is a libFuzzer crash with an automatically-saved
//! reproducer at `crates/dlcp-sim/fuzz/artifacts/ir_stream/`.
//!
//! ## V1.71 chain template caching
//!
//! Building the V1.71 chain costs ~330 µs.  Decoding the cached
//! snapshot costs ~125 µs.  At fuzz speeds (~10⁴ iterations/s
//! target) that's a 2x speedup, so we cache the snapshot bytes
//! in a `OnceLock` and decode it per iteration rather than
//! re-running POR + initial-step seeding from scratch.
//!
//! ## Operator runbook
//!
//! ```bash
//! cd crates/dlcp-sim
//! cargo +nightly fuzz run ir_stream -- -max_total_time=300
//! ```
//!
//! Prereqs (codex P5b.1 scoping notes from 2026-05-04):
//!
//!   * rustup + nightly toolchain (cargo-fuzz needs `-Z` flags).
//!   * `cargo install cargo-fuzz`.
//!
//! Full prereq list lives in `crates/dlcp-sim/fuzz/Cargo.toml`'s
//! header comment (codex LOW from b3d42a8: prior wording pointed
//! at a non-existent README.md).

#![no_main]

use libfuzzer_sys::fuzz_target;

use dlcp_sim::chain::Chain;
use dlcp_sim::clock::ClockDomain;
use dlcp_sim::core::{CoreLoadOptions, core_from_hex_image};
use dlcp_sim::hex::HexImage;
use dlcp_sim::memory::Variant;
use dlcp_sim::reset::ResetSource;
use dlcp_sim::snapshot::{decode, encode};

use std::path::PathBuf;
use std::sync::OnceLock;

const MAX_STIMULI: usize = 8;
const MAX_STEP_TICKS: u32 = 200_000;
/// Core index that receives `InjectUartRxByte` bytes.  V1.71
/// is the only core in this fuzz chain (single-CONTROL build),
/// so the index is hard-coded.  Future multi-core fuzz could
/// take it from the byte stream.
const IR_INJECT_CORE_IDX: usize = 0;

#[derive(Debug, Clone, Copy)]
enum Stimulus {
    StepTicks(u64),
    SetUartBlackout(bool),
    InjectUartRxByte(u8),
}

fn decode_stream(data: &[u8]) -> (u64, Vec<Stimulus>) {
    if data.is_empty() {
        return (0, Vec::new());
    }
    let boot_offset = u64::from(data[0]);
    let mut stims = Vec::with_capacity(MAX_STIMULI);
    // Saturating cap (NOT modulo): byte values 0..=8 produce
    // 0..=8 stimuli; values 9..=255 produce 8 stimuli.  Codex
    // LOW from b3d42a8 flagged the prior `% (MAX_STIMULI + 1)`
    // mapping as contradicting the documented "capped at 8".
    let n = data
        .get(1)
        .map(|b| (usize::from(*b)).min(MAX_STIMULI))
        .unwrap_or(0);
    let body = data.get(2..).unwrap_or(&[]);
    for record in body.chunks_exact(5).take(n) {
        let tag = record[0];
        let payload = u32::from_le_bytes([record[1], record[2], record[3], record[4]]);
        match tag {
            0 => stims.push(Stimulus::StepTicks(
                u64::from(payload.min(MAX_STEP_TICKS)),
            )),
            1 => stims.push(Stimulus::SetUartBlackout((payload & 1) == 1)),
            2 => stims.push(Stimulus::InjectUartRxByte((payload & 0xFF) as u8)),
            _ => { /* skip unknown tag — leaves room for future stimuli */ }
        }
    }
    (boot_offset, stims)
}

fn build_v171_chain(boot_offset: u64) -> Chain {
    let hex_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|p| p.parent())
        .and_then(|p| p.parent())
        .expect("fuzz crate has 3 ancestors back to repo root")
        .join("firmware/patched/releases/DLCP_Control_V1.71.hex");
    let image = HexImage::from_hex_path(&hex_path).expect("V1.71 hex parses");
    let core = core_from_hex_image(
        Variant::Pic18F25K20,
        &image,
        CoreLoadOptions::default(),
    );
    let clock = ClockDomain::new(Variant::Pic18F25K20);
    let mut chain = Chain::new();
    chain.push_core_with_clock(core, clock);
    chain.apply_reset_all(ResetSource::PowerOn);
    chain.schedule_initial_steps(&[boot_offset]);
    chain
}

/// Cached V1.71 template snapshot at boot_offset=0.  We rebuild
/// from scratch when the fuzz input picks a non-zero offset,
/// otherwise we decode the cache.  ~125 µs vs ~330 µs per
/// iteration.
fn template_at_zero_boot_offset() -> &'static [u8] {
    static CELL: OnceLock<Vec<u8>> = OnceLock::new();
    CELL.get_or_init(|| encode(&build_v171_chain(0)))
}

fn apply(chain: &mut Chain, stim: &Stimulus) {
    match stim {
        Stimulus::StepTicks(n) => chain.step_ticks(*n),
        Stimulus::SetUartBlackout(b) => chain.set_uart_blackout(*b),
        Stimulus::InjectUartRxByte(byte) => {
            // We don't care whether the byte was accepted by
            // silicon (SPEN/CREN may be closed); both branches
            // are valid coverage points.  The return is `let _`
            // intentionally.
            let _ = chain.inject_uart_rx_byte(IR_INJECT_CORE_IDX, *byte);
        }
    }
}

fn fuzz_iter(data: &[u8]) {
    let (boot_offset, stims) = decode_stream(data);

    let mut a: Chain = if boot_offset == 0 {
        decode(template_at_zero_boot_offset()).expect("cached template decodes")
    } else {
        build_v171_chain(boot_offset)
    };
    let mut b: Chain = if boot_offset == 0 {
        decode(template_at_zero_boot_offset()).expect("cached template decodes")
    } else {
        build_v171_chain(boot_offset)
    };

    for s in &stims {
        apply(&mut a, s);
        apply(&mut b, s);
    }

    // Invariant 1: snapshot round-trip byte-stable.
    let bytes_a = encode(&a);
    let restored = decode(&bytes_a).expect("snapshot decodes");
    let bytes_a2 = encode(&restored);
    assert_eq!(
        bytes_a, bytes_a2,
        "snapshot round-trip drifted under fuzz input ({} stimuli, boot_offset={})",
        stims.len(),
        boot_offset
    );

    // Invariant 2: two chains given the same stimulus stream
    // encode-equal (replay determinism).  Catches HashMap /
    // HashSet iteration-order leaks.
    let bytes_b = encode(&b);
    assert_eq!(
        bytes_a, bytes_b,
        "replay determinism failed under fuzz input ({} stimuli, boot_offset={})",
        stims.len(),
        boot_offset
    );
}

fuzz_target!(|data: &[u8]| {
    fuzz_iter(data);
});
