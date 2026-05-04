//! Negative-coverage tests for `dlcp-sim replay` argv parsing.
//!
//! Locks the regression that codex flagged on commit `b777c7a`
//! (the fix to commit `45cf3a0`'s P5.3 replay CLI): `cmd_replay`
//! used to silently accept `--final-snapshot` / `--trace` with
//! a missing operand because `args.get(i + 1)` returned `None`,
//! which the old code mapped to `Option::None` and continued.
//! The fix made the operand required; this file is the
//! automated negative-coverage codex asked for.
//!
//! Cargo wires `CARGO_BIN_EXE_dlcp-sim` for integration tests
//! built alongside the binary, so we don't have to find the
//! binary path manually.
//!
//! Each test writes a minimal valid case.json to a tempdir,
//! invokes the CLI with a deliberately broken flag layout, and
//! asserts:
//!
//!   * exit code == 1 (the documented usage-error code), AND
//!   * stderr names the offending flag (so a typo in the error
//!     wording would surface as a test failure, not a silent
//!     contract drift).

use std::path::{Path, PathBuf};
use std::process::Command;

const CASE_JSON_V1: &str = r#"{
  "format": "dlcp-sim-replay-v1",
  "initial_factory": "empty",
  "stimuli": [{"step_ticks": 1000}],
  "expect_final_snapshot_hex": null
}"#;

/// Auto-cleanup wrapper for a per-test scratch directory.
/// Codex review of 661d78b correctly flagged that the prior
/// `tempdir()` returned a bare `PathBuf` and never deleted the
/// directory, despite the comment claiming Drop cleanup; that
/// leaked five unique dirs per test run under
/// `std::env::temp_dir()`.  This struct removes the directory
/// (best-effort -- ignore I/O errors so a failing test
/// doesn't double-fail on cleanup) when the test's
/// `TempDir` binding goes out of scope.
struct TempDir(PathBuf);

impl TempDir {
    fn path(&self) -> &Path {
        self.0.as_path()
    }
}

impl Drop for TempDir {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

fn cli_binary() -> PathBuf {
    PathBuf::from(env!("CARGO_BIN_EXE_dlcp-sim"))
}

fn write_case(dir: &Path, name: &str) -> PathBuf {
    let p = dir.join(name);
    std::fs::write(&p, CASE_JSON_V1).expect("write case.json");
    p
}

fn run(args: &[&str]) -> (i32, String, String) {
    let cp = Command::new(cli_binary())
        .args(args)
        .output()
        .expect("spawn dlcp-sim");
    let code = cp.status.code().unwrap_or(-1);
    let stdout = String::from_utf8_lossy(&cp.stdout).into_owned();
    let stderr = String::from_utf8_lossy(&cp.stderr).into_owned();
    (code, stdout, stderr)
}

/// `--trace` with NO operand should exit 1 and name the flag.
#[test]
fn trace_missing_operand_exits_1() {
    let dir = tempdir();
    let case = write_case(dir.path(), "case.json");
    let (code, _stdout, stderr) =
        run(&["replay", case.to_str().unwrap(), "--trace"]);
    assert_eq!(code, 1, "expected exit 1, got {code} (stderr: {stderr})");
    assert!(
        stderr.contains("--trace"),
        "stderr must name the flag; got: {stderr}"
    );
}

/// `--final-snapshot` followed by `--trace <path>` is treated
/// as a missing operand for `--final-snapshot` (because the
/// next token is a flag, not a path).
#[test]
fn final_snapshot_followed_by_trace_flag_exits_1() {
    let dir = tempdir();
    let case = write_case(dir.path(), "case.json");
    let trace = dir.path().join("trace.txt");
    let (code, _stdout, stderr) = run(&[
        "replay",
        case.to_str().unwrap(),
        "--final-snapshot",
        "--trace",
        trace.to_str().unwrap(),
    ]);
    assert_eq!(code, 1, "expected exit 1, got {code} (stderr: {stderr})");
    assert!(
        stderr.contains("--final-snapshot"),
        "stderr must name --final-snapshot; got: {stderr}"
    );
}

/// `--trace a --trace b` is rejected as a duplicate spec.
#[test]
fn duplicate_trace_flag_exits_1() {
    let dir = tempdir();
    let case = write_case(dir.path(), "case.json");
    let a = dir.path().join("a.txt");
    let b = dir.path().join("b.txt");
    let (code, _stdout, stderr) = run(&[
        "replay",
        case.to_str().unwrap(),
        "--trace",
        a.to_str().unwrap(),
        "--trace",
        b.to_str().unwrap(),
    ]);
    assert_eq!(code, 1, "expected exit 1, got {code} (stderr: {stderr})");
    assert!(
        stderr.contains("--trace") && stderr.contains("twice"),
        "stderr must name --trace and 'twice'; got: {stderr}"
    );
}

/// `--final-snapshot a --final-snapshot b` is also rejected.
/// Mirror of the `--trace` duplicate check, asserting the
/// duplicate-detection covers BOTH flags (codex's review wanted
/// reverse-order coverage too).
#[test]
fn duplicate_final_snapshot_flag_exits_1() {
    let dir = tempdir();
    let case = write_case(dir.path(), "case.json");
    let a = dir.path().join("a.bin");
    let b = dir.path().join("b.bin");
    let (code, _stdout, stderr) = run(&[
        "replay",
        case.to_str().unwrap(),
        "--final-snapshot",
        a.to_str().unwrap(),
        "--final-snapshot",
        b.to_str().unwrap(),
    ]);
    assert_eq!(code, 1, "expected exit 1, got {code} (stderr: {stderr})");
    assert!(
        stderr.contains("--final-snapshot") && stderr.contains("twice"),
        "stderr must name --final-snapshot and 'twice'; got: {stderr}"
    );
}

/// Valid invocation must still succeed (regression guard
/// against over-zealous future hardening that breaks the happy
/// path).
#[test]
fn valid_replay_exits_0_and_writes_trace() {
    let dir = tempdir();
    let case = write_case(dir.path(), "case.json");
    let trace = dir.path().join("trace.txt");
    let (code, _stdout, stderr) = run(&[
        "replay",
        case.to_str().unwrap(),
        "--trace",
        trace.to_str().unwrap(),
    ]);
    assert_eq!(code, 0, "expected exit 0, got {code} (stderr: {stderr})");
    let body = std::fs::read_to_string(&trace).expect("trace exists");
    assert!(
        body.contains("step_ticks 1000"),
        "trace must record the stimulus; got: {body:?}"
    );
}

/// Per-test unique scratch directory under `std::env::temp_dir()`.
/// Returns a `TempDir` whose `Drop` impl removes the directory
/// (best-effort).  Codex review of 661d78b: the prior helper
/// returned a bare `PathBuf` and never cleaned up despite the
/// "deleted on Drop" comment.
fn tempdir() -> TempDir {
    let base = std::env::temp_dir().join(format!(
        "dlcp_sim_cli_argv_{}_{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    std::fs::create_dir_all(&base).expect("mk tempdir");
    TempDir(base)
}
