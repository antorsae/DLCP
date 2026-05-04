//! Phase 5 (P5.4) soak harness for snapshot/replay invariants on
//! [`dlcp_sim::chain::Chain`].
//!
//! Spec reference: `docs/SIM_REWRITE_RUST_SPEC.md` §9 P5.4.  Each
//! soak test runs ≥ 10⁴ scenarios.  Failures dump the seed +
//! stimulus stream to
//! `artifacts/sim_soak_failures/<test>_seed_<idx>.json` for
//! triage with `dlcp-sim replay`.
//!
//! Why a separate harness from `snapshot_property.rs` (P5.2)?
//! Proptest is configured for 64 cases per property -- enough for
//! a per-commit smoke test, not enough to catch rare interactions
//! that only show up at scale (HashMap iteration, integer-overflow
//! corner cases, event-queue tie-breaking, etc.).  The soak
//! harness sweeps a fixed deterministic seed corpus (0..10000) so
//! a CI failure is always reproducible from the dumped seed; no
//! reliance on proptest shrinking heuristics.
//!
//! Design choices:
//!
//!   * **Hand-rolled xorshift64 RNG.**  We don't pull `rand` just
//!     for soak — the existing workspace deps don't include it,
//!     and xorshift64 with the canonical Marsaglia constants
//!     (13/7/17) gives a 2⁶⁴-1 period which is plenty for ≤ 10⁴
//!     scenarios × ≤ 16 stimuli = 1.6×10⁵ draws per test.  Seed
//!     `0` is escaped to `0x9E37_79B9_7F4A_7C15` (the golden ratio
//!     constant -- xorshift64 is degenerate at seed=0).
//!   * **Decode-cached V1.71 chain.**  Building the V1.71 chain
//!     fresh costs ~330 µs (POR + initial-step seeding), but
//!     `decode(snapshot_bytes)` of a pre-built template costs
//!     ~125 µs.  10⁴ scenarios × 0.2 ms saved = 2 s wall.  Also
//!     ensures every scenario starts from byte-identical state,
//!     so any divergence is purely stimulus-driven, not boot-RNG.
//!   * **Step-split soak.**  `chain.step_ticks(N)` must equal
//!     `chain.step_ticks(a) + chain.step_ticks(N-a)` byte-for-byte
//!     for any split point `a ∈ [0, N]`.  Catches universal-clock
//!     scheduler drift that wouldn't surface in single-step
//!     property tests.
//!
//! On failure each test writes
//! `artifacts/sim_soak_failures/<test_name>_seed_<idx>.json` with
//! `{seed, stimuli, observed_bytes_len, expected_bytes_len}` so
//! the operator can rebuild a `dlcp-sim replay`-compatible case
//! by hand for triage.

use dlcp_sim::chain::Chain;
use dlcp_sim::clock::ClockDomain;
use dlcp_sim::core::{CoreLoadOptions, core_from_hex_image};
use dlcp_sim::hex::HexImage;
use dlcp_sim::memory::Variant;
use dlcp_sim::reset::ResetSource;
use dlcp_sim::snapshot::{decode, encode};
use serde::Serialize;
use std::path::PathBuf;
use std::sync::OnceLock;

/// Number of soak scenarios per `#[test]` function.  The spec
/// (`docs/SIM_REWRITE_RUST_SPEC.md` §9 P5.4) requires ≥ 10⁴.
const SOAK_SCENARIOS: u64 = 10_000;

/// Maximum stimuli per scenario.  Each scenario draws
/// `[0..MAX_STIMULI]` from the RNG; tail-only zero-stimulus
/// scenarios still run a snapshot round-trip.
const MAX_STIMULI: u32 = 8;

/// Maximum tick advance per StepTicks stimulus.  Matches the
/// `0..=2_000_000` bound in the proptest property test so
/// soak coverage extends the same regime.
const MAX_STEP_TICKS: u64 = 2_000_000;

/// xorshift64 RNG -- no external crate.  Marsaglia constants
/// 13/7/17 give period 2⁶⁴-1.
#[derive(Debug, Clone, Copy)]
struct Xorshift64(u64);

impl Xorshift64 {
    fn new(seed: u64) -> Self {
        // xorshift64 is degenerate at state=0; replace with the
        // golden-ratio constant so seed `0` is still a valid
        // soak case.
        let s = if seed == 0 { 0x9E37_79B9_7F4A_7C15 } else { seed };
        Self(s)
    }
    fn next_u64(&mut self) -> u64 {
        let mut x = self.0;
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        self.0 = x;
        x
    }
    /// Uniform `[0, n)`.  Modulo bias is acceptable for soak
    /// stimulus generation -- we're not running statistical
    /// tests over the RNG output.
    fn gen_below(&mut self, n: u64) -> u64 {
        if n == 0 {
            0
        } else {
            self.next_u64() % n
        }
    }
}

/// One stimulus.  Mirrors `crates/dlcp-sim-cli/src/main.rs::Stimulus`
/// (case JSON v1) so dumped failures are reproducible via
/// `dlcp-sim replay`.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "snake_case")]
enum Stimulus {
    StepTicks(u64),
    SetUartBlackout(bool),
}

fn draw_stimuli(rng: &mut Xorshift64) -> Vec<Stimulus> {
    let n = rng.gen_below(MAX_STIMULI as u64 + 1) as usize;
    let mut out = Vec::with_capacity(n);
    for _ in 0..n {
        let pick = rng.gen_below(2);
        if pick == 0 {
            out.push(Stimulus::StepTicks(rng.gen_below(MAX_STEP_TICKS + 1)));
        } else {
            out.push(Stimulus::SetUartBlackout(rng.gen_below(2) == 1));
        }
    }
    out
}

fn apply(chain: &mut Chain, stim: &Stimulus) {
    match stim {
        Stimulus::StepTicks(n) => chain.step_ticks(*n),
        Stimulus::SetUartBlackout(b) => chain.set_uart_blackout(*b),
    }
}

fn build_v171_control_chain() -> Chain {
    let hex_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|p| p.parent())
        .expect("crate dir has 2 ancestors")
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
    chain.schedule_initial_steps(&[0]);
    chain
}

/// Decode-cached V1.71 template.  Building the V1.71 chain costs
/// ~330 µs; decoding the cached snapshot costs ~125 µs.  At 10⁴
/// scenarios that's ~2 s saved.  Cache is per-process (one
/// `OnceLock` per cargo-test binary).
fn v171_template_bytes() -> &'static [u8] {
    static CELL: OnceLock<Vec<u8>> = OnceLock::new();
    CELL.get_or_init(|| encode(&build_v171_control_chain()))
}

/// Triage fields embedded under `_meta` inside the dumped
/// case.json so a future operator can correlate the file with
/// the panic line without grepping the whole soak corpus.  The
/// CLI's `Case` struct does not set
/// `#[serde(deny_unknown_fields)]` (see
/// `crates/dlcp-sim-cli/src/main.rs::Case`) so the extra key is
/// silently ignored at replay time -- the file remains a
/// fully-valid `dlcp-sim-replay-v1` case.
#[derive(Serialize)]
struct DumpMeta<'a> {
    test: &'a str,
    seed: u64,
    scenario_idx: u64,
    note: &'a str,
}

/// Write a `dlcp-sim-replay-v1`-shaped case.json under
/// `artifacts/sim_soak_failures/` so the operator can replay
/// the failing scenario directly with
/// `target/release/dlcp-sim replay <path>`.  `factory` is
/// `"empty"` or `"v171_control"`; both are accepted by the CLI's
/// `build_initial_chain` (see `crates/dlcp-sim-cli/src/main.rs`).
/// `kind`, when present, is appended to the filename so a
/// step-split failure dumps both legs of the comparison without
/// collision (`<test>_seed_<idx>_whole.json` vs
/// `<test>_seed_<idx>_split.json`).
///
/// Stays infallible -- if the dump dir or write fails we just
/// append the I/O error to the returned suffix instead of
/// masking the soak panic.
fn dump_replay_case(
    test: &str,
    seed: u64,
    scenario_idx: u64,
    factory: &str,
    stimuli: &[Stimulus],
    note: &str,
    kind: Option<&str>,
) -> String {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|p| p.parent())
        .expect("crate dir has 2 ancestors")
        .join("artifacts/sim_soak_failures");
    let kind_part = kind.map(|k| format!("_{k}")).unwrap_or_default();
    let path = dir.join(format!(
        "{test}_seed_{scenario_idx:05}{kind_part}.json"
    ));
    let case = serde_json::json!({
        "format": "dlcp-sim-replay-v1",
        "initial_factory": factory,
        "stimuli": stimuli,
        "expect_final_snapshot_hex": null,
        "_meta": DumpMeta {
            test,
            seed,
            scenario_idx,
            note,
        },
    });
    let body = serde_json::to_string_pretty(&case)
        .unwrap_or_else(|e| format!("<dump-serialize-failed: {e}>"));
    let mut suffix = String::new();
    if let Err(e) = std::fs::create_dir_all(&dir) {
        suffix.push_str(&format!(" (dump-dir create failed: {e})"));
    } else if let Err(e) = std::fs::write(&path, &body) {
        suffix.push_str(&format!(" (dump-write failed: {e})"));
    } else {
        suffix.push_str(&format!(" (dumped to {})", path.display()));
    }
    suffix
}

/// Empty-chain snapshot round-trip soak: 10⁴ scenarios.  For each
/// scenario, apply a random stimulus stream, then assert
/// `encode(decode(b)) == b` (byte-stable).
#[test]
fn empty_chain_round_trip_soak() {
    for scenario_idx in 0..SOAK_SCENARIOS {
        let seed = 0xA5A5_A5A5_0000_0000 ^ scenario_idx;
        let mut rng = Xorshift64::new(seed);
        let stims = draw_stimuli(&mut rng);
        let mut chain = Chain::new();
        for s in &stims {
            apply(&mut chain, s);
        }
        let bytes = encode(&chain);
        let restored = match decode(&bytes) {
            Ok(c) => c,
            Err(e) => {
                let suffix = dump_replay_case(
                    "empty_chain_round_trip_soak",
                    seed,
                    scenario_idx,
                    "empty",
                    &stims,
                    &format!("decode failed: {e}"),
                    None,
                );
                panic!(
                    "soak scenario {scenario_idx} (seed {seed:#018x}) decode \
                     failed: {e}{suffix}"
                );
            }
        };
        let bytes2 = encode(&restored);
        if bytes != bytes2 {
            let suffix = dump_replay_case(
                "empty_chain_round_trip_soak",
                seed,
                scenario_idx,
                "empty",
                &stims,
                &format!(
                    "round-trip not byte-stable: {} vs {} bytes",
                    bytes.len(),
                    bytes2.len()
                ),
                None,
            );
            panic!(
                "soak scenario {scenario_idx} (seed {seed:#018x}) byte-stable \
                 round-trip failed: {} vs {} bytes{suffix}",
                bytes.len(),
                bytes2.len()
            );
        }
    }
}

/// Empty-chain replay determinism soak: two empty chains given
/// identical stimulus streams must encode-equal.  Catches
/// HashMap/HashSet iteration-order leaks and per-instance hidden
/// state.
#[test]
fn empty_chain_replay_determinism_soak() {
    for scenario_idx in 0..SOAK_SCENARIOS {
        let seed = 0xDEAD_BEEF_0000_0000 ^ scenario_idx;
        let mut rng = Xorshift64::new(seed);
        let stims = draw_stimuli(&mut rng);
        let mut a = Chain::new();
        let mut b = Chain::new();
        for s in &stims {
            apply(&mut a, s);
            apply(&mut b, s);
        }
        let ba = encode(&a);
        let bb = encode(&b);
        if ba != bb {
            let suffix = dump_replay_case(
                "empty_chain_replay_determinism_soak",
                seed,
                scenario_idx,
                "empty",
                &stims,
                &format!(
                    "replay-determinism: a={} b={} bytes",
                    ba.len(),
                    bb.len()
                ),
                None,
            );
            panic!(
                "soak scenario {scenario_idx} (seed {seed:#018x}) \
                 replay-determinism failed: a={} b={} bytes{suffix}",
                ba.len(),
                bb.len()
            );
        }
    }
}

/// V1.71 control-chain snapshot round-trip soak: 10⁴ scenarios.
/// Each scenario decodes the cached V1.71 template, applies
/// random stimuli, asserts byte-stable round-trip.  Exercises
/// real `Core`/`Memory`/`HexImage`/`EventQueue`/`ClockDomain`
/// serde paths under PIC18 instruction execution.
#[test]
fn v171_chain_round_trip_soak() {
    let template = v171_template_bytes();
    for scenario_idx in 0..SOAK_SCENARIOS {
        let seed = 0xCAFE_F00D_0000_0000 ^ scenario_idx;
        let mut rng = Xorshift64::new(seed);
        let stims = draw_stimuli(&mut rng);
        let mut chain: Chain = decode(template).expect("template decodes");
        for s in &stims {
            apply(&mut chain, s);
        }
        let bytes = encode(&chain);
        let restored = match decode(&bytes) {
            Ok(c) => c,
            Err(e) => {
                let suffix = dump_replay_case(
                    "v171_chain_round_trip_soak",
                    seed,
                    scenario_idx,
                    "v171_control",
                    &stims,
                    &format!("decode failed: {e}"),
                    None,
                );
                panic!(
                    "soak scenario {scenario_idx} (seed {seed:#018x}) \
                     v171 decode failed: {e}{suffix}"
                );
            }
        };
        let bytes2 = encode(&restored);
        if bytes != bytes2 {
            let suffix = dump_replay_case(
                "v171_chain_round_trip_soak",
                seed,
                scenario_idx,
                "v171_control",
                &stims,
                &format!(
                    "round-trip not byte-stable: {} vs {} bytes",
                    bytes.len(),
                    bytes2.len()
                ),
                None,
            );
            panic!(
                "soak scenario {scenario_idx} (seed {seed:#018x}) v171 \
                 byte-stable round-trip failed: {} vs {} bytes{suffix}",
                bytes.len(),
                bytes2.len()
            );
        }
    }
}

/// V1.71 control-chain replay determinism soak: two V1.71 chains
/// (both decoded from the same template) given identical stimulus
/// streams must encode-equal.  Catches per-instance hidden state
/// in real-firmware peripherals (oscillator, EUSART, MSSP, GPIO,
/// EEPROM, ADC, USB, IRQ, timers).
#[test]
fn v171_chain_replay_determinism_soak() {
    let template = v171_template_bytes();
    for scenario_idx in 0..SOAK_SCENARIOS {
        let seed = 0xFEED_FACE_0000_0000 ^ scenario_idx;
        let mut rng = Xorshift64::new(seed);
        let stims = draw_stimuli(&mut rng);
        let mut a: Chain = decode(template).expect("template decodes");
        let mut b: Chain = decode(template).expect("template decodes");
        for s in &stims {
            apply(&mut a, s);
            apply(&mut b, s);
        }
        let ba = encode(&a);
        let bb = encode(&b);
        if ba != bb {
            let suffix = dump_replay_case(
                "v171_chain_replay_determinism_soak",
                seed,
                scenario_idx,
                "v171_control",
                &stims,
                &format!(
                    "v171 replay-determinism: a={} b={} bytes",
                    ba.len(),
                    bb.len()
                ),
                None,
            );
            panic!(
                "soak scenario {scenario_idx} (seed {seed:#018x}) v171 \
                 replay-determinism failed: a={} b={} bytes{suffix}",
                ba.len(),
                bb.len()
            );
        }
    }
}

/// Step-split soak: for any random `(N, a)` with `0 ≤ a ≤ N`,
/// `chain.step_ticks(N)` must equal
/// `chain.step_ticks(a); chain.step_ticks(N-a)` byte-for-byte on
/// the V1.71 chain.  Catches universal-clock scheduler drift
/// where the choice of step boundary changes which events fire
/// in which order -- a class of bugs that single-step property
/// tests cannot reach.
#[test]
fn step_split_soak() {
    let template = v171_template_bytes();
    for scenario_idx in 0..SOAK_SCENARIOS {
        let seed = 0xBAAD_CAFE_0000_0000 ^ scenario_idx;
        let mut rng = Xorshift64::new(seed);
        // Cap N at 1 M tick so the soak finishes in budget; the
        // largest interesting events on V1.71 are timer/ADC
        // periodics measured in tens-of-thousands of ticks, so 1
        // M tick is enough to cross several event boundaries.
        let n = rng.gen_below(1_000_000 + 1);
        let a = rng.gen_below(n + 1);

        let mut whole: Chain = decode(template).expect("template decodes");
        whole.step_ticks(n);
        let bytes_whole = encode(&whole);

        let mut split: Chain = decode(template).expect("template decodes");
        split.step_ticks(a);
        split.step_ticks(n - a);
        let bytes_split = encode(&split);

        if bytes_whole != bytes_split {
            // Step-split divergence is a comparison of two
            // separate executions, not a single stimulus stream.
            // Dump both legs as fully-valid replay cases so the
            // operator can `dlcp-sim replay` each one and diff
            // the resulting `--final-snapshot` outputs (the
            // soak panic message names both files).
            let note = format!(
                "step-split divergence at N={n} a={a}: whole={} split={}",
                bytes_whole.len(),
                bytes_split.len()
            );
            let suffix_whole = dump_replay_case(
                "step_split_soak",
                seed,
                scenario_idx,
                "v171_control",
                &[Stimulus::StepTicks(n)],
                &note,
                Some("whole"),
            );
            let suffix_split = dump_replay_case(
                "step_split_soak",
                seed,
                scenario_idx,
                "v171_control",
                &[Stimulus::StepTicks(a), Stimulus::StepTicks(n - a)],
                &note,
                Some("split"),
            );
            panic!(
                "soak scenario {scenario_idx} (seed {seed:#018x}) step-split \
                 failed at N={n} a={a}: whole={} bytes vs split={} \
                 bytes{suffix_whole}{suffix_split}",
                bytes_whole.len(),
                bytes_split.len()
            );
        }
    }
}

/// Auto-cleanup wrapper for the synthetic dump file written by
/// `dump_replay_case_is_replay_v1_shape`.  Removes the file on
/// drop -- including panic unwinding -- so a failing assertion
/// doesn't leave a stray synthetic dump in
/// `artifacts/sim_soak_failures/` that an operator might mistake
/// for a real soak failure (codex LOW from 5b15006).
struct DumpArtifact(PathBuf);

impl Drop for DumpArtifact {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.0);
    }
}

/// Self-test for `dump_replay_case`: a dump must round-trip
/// through `serde_json` as a `dlcp-sim-replay-v1` case
/// (`format`, `initial_factory`, `stimuli` all present and
/// well-typed) and the embedded `_meta` must carry the
/// triage context.  Locks codex's MEDIUM finding from
/// the review of 661d78b -- failure dumps must be
/// `dlcp-sim replay`-compatible, not just diagnostic blobs.
///
/// This test deliberately does NOT touch
/// `artifacts/sim_soak_failures/` -- it inspects the
/// serialized JSON shape directly.  We avoid invoking the
/// `dlcp-sim` CLI binary because the soak test crate
/// belongs to `dlcp-sim` (the library), not `dlcp-sim-cli`,
/// and we don't want the soak crate to depend on the CLI
/// binary build artifact.
#[test]
fn dump_replay_case_is_replay_v1_shape() {
    let stims = vec![
        Stimulus::StepTicks(1234),
        Stimulus::SetUartBlackout(true),
    ];
    // Use a PID-derived synthetic scenario_idx so two
    // concurrent cargo-test runs don't share the same dump
    // file path (codex LOW from 5b15006: deterministic path
    // collision risk).  Stays well above SOAK_SCENARIOS so
    // it's obviously synthetic.
    let synthetic_idx: u64 = u64::from(std::process::id())
        .wrapping_add(SOAK_SCENARIOS * 100);
    let _suffix = dump_replay_case(
        "dump_replay_case_is_replay_v1_shape",
        0xDEAD,
        synthetic_idx,
        "v171_control",
        &stims,
        "self-test",
        Some("selftest"),
    );
    let dump_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|p| p.parent())
        .expect("crate dir has 2 ancestors")
        .join(format!(
            "artifacts/sim_soak_failures/\
             dump_replay_case_is_replay_v1_shape_seed_{synthetic_idx:05}_selftest.json"
        ));
    // Wrap the dump path in DumpArtifact BEFORE the
    // assertions so the file is cleaned up even if an
    // assertion panics.  (Codex LOW from 5b15006: previous
    // version only removed the file on the success path.)
    let _cleanup = DumpArtifact(dump_path.clone());
    let body = std::fs::read_to_string(&dump_path)
        .expect("self-test dump exists");
    let v: serde_json::Value =
        serde_json::from_str(&body).expect("dump parses as JSON");

    // case.json v1 contract:
    assert_eq!(v["format"], "dlcp-sim-replay-v1");
    assert_eq!(v["initial_factory"], "v171_control");
    assert!(v["stimuli"].is_array(), "stimuli must be an array");
    assert_eq!(v["stimuli"].as_array().unwrap().len(), 2);
    assert_eq!(
        v["stimuli"][0]["step_ticks"], 1234,
        "first stim must be step_ticks(1234)"
    );
    assert_eq!(
        v["stimuli"][1]["set_uart_blackout"], true,
        "second stim must be set_uart_blackout(true)"
    );
    // `serde_json::Value` indexing returns `Value::Null` for
    // a MISSING key as well as for a key whose value is null.
    // To prove the field is actually present (not just
    // missing-and-defaulted-to-null), pin both the
    // `as_object().contains_key(...)` flag and the value
    // (codex LOW from 5b15006: prior assertion would pass
    // even if the writer dropped the field entirely).
    let obj = v.as_object().expect("dump root must be an object");
    assert!(
        obj.contains_key("expect_final_snapshot_hex"),
        "expect_final_snapshot_hex key must be PRESENT in dump"
    );
    assert!(
        v["expect_final_snapshot_hex"].is_null(),
        "expect_final_snapshot_hex value must be null"
    );

    // Triage context lives under `_meta` (CLI ignores
    // unknown keys, so this is OK).
    assert_eq!(v["_meta"]["test"], "dump_replay_case_is_replay_v1_shape");
    assert_eq!(v["_meta"]["seed"], 0xDEAD);
    assert_eq!(v["_meta"]["scenario_idx"], synthetic_idx);
    assert_eq!(v["_meta"]["note"], "self-test");

    // _cleanup drops here, removing the synthetic artifact.
    // (Drop fires on panic unwinding too, so a failed
    // assertion above still cleans up.)
}
