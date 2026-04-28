//! PyO3 wrapper crate for `dlcp-sim`.
//!
//! P4.1 establishes the minimum-viable Python extension
//! module: `import dlcp_sim_native; dlcp_sim_native.__version__`
//! must work after `cargo build --release && bash build.sh`
//! from the crate directory.  Subsequent P4.2+ sub-tasks
//! layer the `Chain`, `Core`, `step_ticks`, `lcd_lines()`,
//! etc. API on top of this minimal stub.
//!
//! The module name `dlcp_sim_native` comes from
//! `[lib] name = "dlcp_sim_native"` in `Cargo.toml`; PyO3
//! requires the `#[pymodule]` function name to match the
//! cdylib's library name (minus the `lib` prefix on Unix).

use pyo3::prelude::*;

/// `dlcp_sim_native` Python module.
///
/// Today's surface is intentionally tiny: just `__version__`.
/// Each P4.x sub-task incrementally adds bindings until the
/// full `chain_gpsim.py` API surface (per spec §3) is
/// available natively.
#[pymodule]
fn dlcp_sim_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
