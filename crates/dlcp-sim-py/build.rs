//! Cargo build-script: emits the macOS `-undefined
//! dynamic_lookup` / `-flat_namespace` linker flags via
//! PyO3's official helper, regardless of the cargo
//! invocation cwd.
//!
//! Why a `build.rs` rather than `.cargo/config.toml`:
//! cargo only reads `.cargo/config.toml` when invoked from
//! the file's directory or below.  `cargo build -p
//! dlcp-sim-py` (or `cargo test --workspace`) from the
//! workspace root does NOT pick up this crate's local
//! `.cargo/config.toml`, which silently broke macOS
//! builds.  `pyo3_build_config::add_extension_module_link_args()`
//! emits `cargo:rustc-link-arg=` directives from build.rs
//! itself, which apply unconditionally to this crate's
//! cdylib regardless of cwd.  Codex MEDIUM from 45b041d.
//!
//! The function is a no-op on Linux (whose ELF linker
//! already tolerates undefined shared-lib symbols) and a
//! no-op when the `extension-module` feature is OFF.

fn main() {
    pyo3_build_config::add_extension_module_link_args();
}
