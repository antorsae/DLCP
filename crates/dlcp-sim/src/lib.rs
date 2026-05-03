//! `dlcp-sim` — single-process cycle-perfect PIC18 simulator for the
//! Hypex DLCP chain (1× CONTROL PIC18F25K20 + N× MAIN PIC18F2455).
//!
//! P1.1 lays only the workspace and type skeleton; the ISA decoder,
//! peripheral models, and chain scheduler are built up by later
//! sub-tasks (P1.2..P3.gate).  The crate exposes nothing useful yet
//! beyond the [`Variant`] enum and the empty [`Core`] / [`Memory`]
//! shells later phases hang their behaviour off.

pub mod boot_offset;
pub mod chain;
pub mod clock;
pub mod config;
pub mod core;
pub mod exec;
pub mod hex;
pub mod isa;
pub mod lcd;
pub mod memory;
pub mod peripherals;
pub mod pinnet;
pub mod reset;
pub mod scheduler;
pub mod stack;

pub use crate::config::{BorenMode, Config, FoscMode};
pub use crate::core::{Core, CoreLoadOptions, RunState, core_from_hex_image};
pub use crate::exec::{ExecError, step};
pub use crate::hex::{HexImage, HexLoadError};
pub use crate::isa::{Access, Dest, FsrIndex, Instruction, TableMode, decode};
pub use crate::memory::{Memory, Variant};
pub use crate::reset::{ResetSource, apply_reset};
pub use crate::stack::{Stack, StackEntry};
