//! Cargo build-script: emits cdylib-specific macOS linker
//! flags via PyO3's official helper, regardless of the
//! cargo invocation cwd.
//!
//! Why a `build.rs` rather than `.cargo/config.toml`:
//! cargo only reads `.cargo/config.toml` when invoked from
//! the file's directory or below.  `cargo build -p
//! dlcp-sim-py` from the workspace root does NOT pick up
//! this crate's local `.cargo/config.toml`, which silently
//! broke macOS builds (codex MEDIUM from 45b041d).
//!
//! What the helper actually does (per pyo3-build-config
//! 0.28.3 source): on `cfg(target_os = "macos")` it emits
//!     cargo:rustc-cdylib-link-arg=-undefined
//!     cargo:rustc-cdylib-link-arg=dynamic_lookup
//! These are CDYLIB-SPECIFIC link args, applied to the
//! crate's `[lib] crate-type = ["cdylib"]` output.  They
//! do NOT apply to `cargo test` binaries / `cargo run`
//! examples / etc., so a future `cargo test` inside this
//! crate that links against pyo3 would still hit the
//! `_Py_*` link errors -- we'll address that in P4.2 if it
//! comes up.  On Linux (ELF) the helper is a no-op --
//! ELF linkers tolerate undefined shared-lib symbols by
//! default, so no extra flags are needed.  On
//! `wasm32-unknown-emscripten` the helper emits its own
//! emscripten-specific cdylib link args (`-sSIDE_MODULE=2`,
//! `-sWASM_BIGINT`); we don't target wasm today but the
//! comment used to call those targets "no-op", which was
//! wrong.

fn main() {
    pyo3_build_config::add_extension_module_link_args();
}
