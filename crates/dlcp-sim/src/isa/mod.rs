//! PIC18 ISA: instruction representation, decoder, and (later)
//! executor.  P1.2 lays the decoder; P1.3 (Access-Bank semantics
//! threading), P1.4 (FSR addressing modes), P1.5 (hardware stack),
//! P1.6 (reset sources), and P1.7 (config-bit parser) build the
//! actual interpreter that consumes [`decode::Instruction`]s.
//!
//! Reference: DS39632E §24 (PIC18F2455 instruction set) and
//! DS41303G §25 (PIC18F25K20 instruction set).  The encoding is
//! byte-for-byte identical between the two variants — the only
//! difference is which SFR addresses are alive — so a single
//! decoder handles both.

pub mod decode;
pub mod fsr;

pub use crate::isa::decode::{
    Access, Dest, FsrIndex, Instruction, TableMode, decode,
};
pub use crate::isa::fsr::{FsrAccessMode, classify_fsr_indirect, fsr_high_addr, fsr_low_addr};
