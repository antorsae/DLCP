//! `dlcp-sim` replay CLI.
//!
//! Phase 5 (P5.3) deliverable per `docs/SIM_REWRITE_RUST_SPEC.md` §9.
//!
//! ```text
//! dlcp-sim replay <case.json> [--final-snapshot <path>] [--trace <path>]
//! ```
//!
//! Reads a `case.json` describing an initial chain state + stimulus
//! stream, runs the simulator, optionally writes a final snapshot
//! and/or an action-level trace.  The case format is versioned
//! (`format: "dlcp-sim-replay-v1"`).
//!
//! ## Case JSON schema (v1)
//!
//! ```json
//! {
//!   "format": "dlcp-sim-replay-v1",
//!   "initial_factory": "v171_control" | "empty",
//!   "initial_snapshot_hex": "lowercase hex of bincode bytes" | null,
//!   "stimuli": [
//!     {"step_ticks": 1000000},
//!     {"set_uart_blackout": true},
//!     {"set_uart_blackout": false}
//!   ],
//!   "expect_final_snapshot_hex": "..." | null
//! }
//! ```
//!
//! Exactly one of `initial_factory` or `initial_snapshot_hex` must
//! be set.  `expect_final_snapshot_hex`, if set, is checked
//! byte-for-byte against the post-stimulus snapshot; mismatch
//! causes exit code 3.
//!
//! ## Exit codes
//!
//! * 0 — replay succeeded; if `expect_final_snapshot_hex` was set,
//!   it matched.
//! * 1 — usage error (bad argv, missing file, parse error).
//! * 2 — replay failed (stimulus invalid, snapshot decode failed).
//! * 3 — `expect_final_snapshot_hex` mismatch.

use std::io::Write;
use std::path::Path;
use std::process::ExitCode;

use dlcp_sim::chain::Chain;
use dlcp_sim::clock::ClockDomain;
use dlcp_sim::core::{CoreLoadOptions, core_from_hex_image};
use dlcp_sim::hex::HexImage;
use dlcp_sim::memory::Variant;
use dlcp_sim::reset::ResetSource;
use dlcp_sim::snapshot;
use serde::{Deserialize, Serialize};

const FORMAT: &str = "dlcp-sim-replay-v1";

#[derive(Debug, Serialize, Deserialize)]
struct Case {
    format: String,
    #[serde(default)]
    initial_factory: Option<String>,
    #[serde(default)]
    initial_snapshot_hex: Option<String>,
    stimuli: Vec<Stimulus>,
    #[serde(default)]
    expect_final_snapshot_hex: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
enum Stimulus {
    StepTicks(u64),
    SetUartBlackout(bool),
}

fn print_usage(program: &str) {
    eprintln!(
        "usage: {program} replay <case.json> \
         [--final-snapshot <path>] [--trace <path>]\n\
         \n\
         see crates/dlcp-sim-cli/src/main.rs for the case.json schema."
    );
}

fn build_initial_chain(case: &Case) -> Result<Chain, String> {
    match (case.initial_factory.as_deref(), case.initial_snapshot_hex.as_deref()) {
        (Some(_), Some(_)) => Err(
            "case must set EXACTLY ONE of initial_factory or initial_snapshot_hex"
                .to_string(),
        ),
        (None, None) => Err(
            "case must set ONE of initial_factory or initial_snapshot_hex"
                .to_string(),
        ),
        (Some("empty"), None) => Ok(Chain::new()),
        (Some("v171_control"), None) => build_v171_control_chain()
            .map_err(|e| format!("v171_control build failed: {e}")),
        (Some(other), None) => Err(format!("unknown initial_factory: {other:?}")),
        (None, Some(hex)) => {
            let bytes = decode_hex(hex)?;
            snapshot::decode(&bytes).map_err(|e| format!("snapshot decode: {e}"))
        }
    }
}

fn build_v171_control_chain() -> Result<Chain, String> {
    let hex_path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|p| p.parent())
        .ok_or("crate dir has no grandparent")?
        .join("firmware/patched/releases/DLCP_Control_V1.71.hex");
    let image = HexImage::from_hex_path(&hex_path)
        .map_err(|e| format!("V1.71 hex parse: {e:?}"))?;
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
    Ok(chain)
}

fn decode_hex(s: &str) -> Result<Vec<u8>, String> {
    if s.len() % 2 != 0 {
        return Err(format!("hex blob must have even length; got {}", s.len()));
    }
    let mut out = Vec::with_capacity(s.len() / 2);
    for i in (0..s.len()).step_by(2) {
        let byte = u8::from_str_radix(&s[i..i + 2], 16)
            .map_err(|e| format!("bad hex at offset {i}: {e}"))?;
        out.push(byte);
    }
    Ok(out)
}

fn encode_hex(bytes: &[u8]) -> String {
    let mut s = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        use std::fmt::Write as _;
        write!(s, "{b:02x}").unwrap();
    }
    s
}

fn apply(
    chain: &mut Chain,
    stim: &Stimulus,
    trace: Option<&mut std::fs::File>,
) -> Result<(), String> {
    let summary = match stim {
        Stimulus::StepTicks(n) => {
            chain.step_ticks(*n);
            format!("step_ticks {n}")
        }
        Stimulus::SetUartBlackout(b) => {
            chain.set_uart_blackout(*b);
            format!("set_uart_blackout {b}")
        }
    };
    if let Some(f) = trace {
        writeln!(
            f,
            "[tick {tick}] {summary}",
            tick = chain.current_tick
        )
        .map_err(|e| format!("trace write: {e}"))?;
    }
    Ok(())
}

fn cmd_replay(args: &[String]) -> Result<(), (String, u8)> {
    if args.is_empty() {
        return Err(("missing <case.json> argument".to_string(), 1));
    }
    let mut case_path: Option<&str> = None;
    let mut final_snapshot_path: Option<&str> = None;
    let mut trace_path: Option<&str> = None;
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--final-snapshot" => {
                i += 1;
                final_snapshot_path = args.get(i).map(|s| s.as_str());
            }
            "--trace" => {
                i += 1;
                trace_path = args.get(i).map(|s| s.as_str());
            }
            other if !other.starts_with("--") && case_path.is_none() => {
                case_path = Some(other);
            }
            other => return Err((format!("unexpected argument: {other:?}"), 1)),
        }
        i += 1;
    }
    let case_path = case_path.ok_or_else(|| ("missing <case.json>".to_string(), 1))?;
    let case_text = std::fs::read_to_string(case_path)
        .map_err(|e| (format!("read {case_path}: {e}"), 1))?;
    let case: Case = serde_json::from_str(&case_text)
        .map_err(|e| (format!("parse {case_path}: {e}"), 1))?;
    if case.format != FORMAT {
        return Err((
            format!(
                "case format mismatch: expected {FORMAT}, got {actual:?}",
                actual = case.format
            ),
            1,
        ));
    }
    let mut chain = build_initial_chain(&case).map_err(|e| (e, 2))?;

    let mut trace_file = match trace_path {
        Some(p) => Some(
            std::fs::File::create(p)
                .map_err(|e| (format!("open trace {p}: {e}"), 1))?,
        ),
        None => None,
    };
    for s in &case.stimuli {
        apply(&mut chain, s, trace_file.as_mut()).map_err(|e| (e, 2))?;
    }
    let final_bytes = snapshot::encode(&chain);

    if let Some(p) = final_snapshot_path {
        std::fs::write(Path::new(p), &final_bytes)
            .map_err(|e| (format!("write final snapshot {p}: {e}"), 1))?;
    }

    if let Some(expected_hex) = &case.expect_final_snapshot_hex {
        let expected = decode_hex(expected_hex).map_err(|e| (e, 1))?;
        if expected != final_bytes {
            return Err((
                format!(
                    "expect_final_snapshot_hex mismatch: \
                     expected {} bytes, got {} bytes; sha differ",
                    expected.len(),
                    final_bytes.len()
                ),
                3,
            ));
        }
    }

    println!(
        "ok: replayed {n} stimuli; final_tick={tick}; \
         final_snapshot_bytes={bytes}",
        n = case.stimuli.len(),
        tick = chain.current_tick,
        bytes = final_bytes.len()
    );
    Ok(())
}

fn cmd_emit_template(args: &[String]) -> Result<(), (String, u8)> {
    let factory = args.first().map(String::as_str).unwrap_or("empty");
    let case = Case {
        format: FORMAT.to_string(),
        initial_factory: Some(factory.to_string()),
        initial_snapshot_hex: None,
        stimuli: vec![
            Stimulus::StepTicks(1_000_000),
            Stimulus::SetUartBlackout(true),
            Stimulus::SetUartBlackout(false),
            Stimulus::StepTicks(500_000),
        ],
        expect_final_snapshot_hex: None,
    };
    let json = serde_json::to_string_pretty(&case)
        .map_err(|e| (format!("serialize case template: {e}"), 1))?;
    println!("{json}");
    Ok(())
}

fn cmd_encode_hex(args: &[String]) -> Result<(), (String, u8)> {
    let path = args
        .first()
        .ok_or_else(|| ("missing <snapshot.bin>".to_string(), 1))?;
    let bytes = std::fs::read(Path::new(path))
        .map_err(|e| (format!("read {path}: {e}"), 1))?;
    println!("{}", encode_hex(&bytes));
    Ok(())
}

fn main() -> ExitCode {
    let argv: Vec<String> = std::env::args().collect();
    let program = argv.first().cloned().unwrap_or_else(|| "dlcp-sim".to_string());
    let args = &argv[1..];
    let result = match args.first().map(String::as_str) {
        Some("replay") => cmd_replay(&args[1..]),
        Some("emit-template") => cmd_emit_template(&args[1..]),
        Some("encode-hex") => cmd_encode_hex(&args[1..]),
        Some("--help") | Some("-h") | Some("help") | None => {
            print_usage(&program);
            return ExitCode::from(if args.is_empty() { 1 } else { 0 });
        }
        Some(other) => {
            eprintln!("unknown subcommand: {other:?}");
            print_usage(&program);
            return ExitCode::from(1);
        }
    };
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err((msg, code)) => {
            eprintln!("error: {msg}");
            ExitCode::from(code)
        }
    }
}
