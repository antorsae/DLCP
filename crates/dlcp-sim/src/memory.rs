//! PIC18 data-memory model: banked RAM + Access Bank + SFR routing.
//!
//! P1.1 lays only the type skeleton and basic addressing primitives.
//! Per-SFR side effects (e.g. `BAUDCON.BRG16` configuring the
//! UART baud generator) are wired in later phases via peripheral
//! modules; this module's job is the layout itself: which physical
//! byte the `f`-field of an instruction operand resolves to under
//! the `a`-bit Access-Bank semantics, and where the top-of-bank-15
//! SFR area starts on each [`Variant`].
//!
//! ## Variant differences (relevant to addressing)
//!
//! | Variant            | Access-Bank low bound | Access-Bank high bound | SFR window  |
//! |--------------------|-----------------------|-----------------------|-------------|
//! | `Pic18F25K20`      | `0x000-0x05F`         | `0xF60-0xFFF`         | `0xF60-0xFFF` |
//! | `Pic18F2455`       | `0x000-0x05F`         | `0xF60-0xFFF`         | `0xF60-0xFFF` |
//!
//! The two chips share the **same** Access-Bank split (`0x60` low
//! boundary).  The SFR contents differ — the 2455 has the USB
//! endpoint registers at `0xF66-0xF7F` that the K20 doesn't, the
//! K20 has additional pins (PORTC RCSTA2 etc.) etc. — but the
//! addressing arithmetic is identical, so a single `Memory` impl
//! handles both.  Per-variant SFR allocation lives in the
//! peripheral modules (P2).
//!
//! ## RAM layout (data memory; not program memory)
//!
//! Both chips have 4 KiB of physical data memory split into 16
//! banks of 256 bytes:
//!
//! ```text
//! 0x000..=0x0FF  Bank 0      (firmware-defined RAM, IR debounce, etc.)
//! 0x100..=0x1FF  Bank 1
//! ...
//! 0xE00..=0xEFF  Bank 14
//! 0xF00..=0xFFF  Bank 15     (BAUDCON, STATUS, EUSART, MSSP, ...)
//! ```
//!
//! All 4096 bytes are kept in one contiguous backing array; bank
//! arithmetic is purely a property of how instruction operands are
//! resolved, not of how bytes are stored.  See [`Memory::resolve`]
//! for the `a`-bit semantics.

#![allow(dead_code, reason = "P1.1 skeleton; behaviour wired in P1.2+")]

/// Which PIC18 variant this core is modelling.  The variant
/// determines:
///
///   * SFR allocation (which addresses in the `0xF60-0xFFF` window
///     are alive vs. unimplemented).
///   * Pin map, peripheral set, and config-bit layout.  All of those
///     come online with the peripheral modules in P2.
///
/// The two variants share the PIC18 ISA byte-for-byte; a single
/// instruction decoder (P1.2) handles both.
#[derive(Copy, Clone, Eq, PartialEq, Debug, Hash)]
pub enum Variant {
    /// CONTROL MCU.  Datasheet: Microchip DS41303G.
    Pic18F25K20,
    /// MAIN MCU.  Datasheet: Microchip DS39632E (`firmware/reference/39632e.md`).
    Pic18F2455,
}

impl Variant {
    /// Total data memory size in bytes (16 banks × 256 B).  Both
    /// supported variants are 4 KiB.
    pub const fn data_memory_bytes(self) -> usize {
        match self {
            Variant::Pic18F25K20 | Variant::Pic18F2455 => 4096,
        }
    }

    /// Host backing-buffer size in bytes.  Kept at 32 KiB for
    /// both variants so bootloader-seed merge code can reuse one
    /// storage shape; silicon fetch/TBLRD visibility is bounded by
    /// [`Self::implemented_program_memory_bytes`].
    pub const fn program_memory_bytes(self) -> usize {
        match self {
            Variant::Pic18F25K20 => 32 * 1024,
            Variant::Pic18F2455 => 32 * 1024,
        }
    }

    /// Implemented on-die program memory in bytes.  DS39632E
    /// lists PIC18F2455 as 24 KiB (`0x0000..0x5FFF`); DS40001303H
    /// lists PIC18F25K20 as 32 KiB (`0x0000..0x7FFF`).  Addresses
    /// above this limit may exist in the simulator's host buffer
    /// but must read as unimplemented program-memory gap for the
    /// corresponding silicon variant.
    pub const fn implemented_program_memory_bytes(self) -> usize {
        match self {
            Variant::Pic18F25K20 => 32 * 1024,
            Variant::Pic18F2455 => 24 * 1024,
        }
    }

    /// DEVID1/DEVID2 bytes returned at `0x3FFFFE..0x3FFFFF`.
    /// The DEV bits are fixed by the datasheets; REV bits are
    /// silicon-revision-specific, so the simulator reports revision
    /// `0` deterministically.  Anchors:
    /// DS39632E Register 25-14 lists PIC18F2455 as
    /// `DEVID2=0001_0010`, `DEVID1.DEV<2:0>=011`;
    /// DS40001303H Registers 23-12/23-13 list PIC18F25K20 as
    /// `DEVID2=0010_0000`, `DEVID1.DEV<2:0>=011`.
    pub const fn devid_bytes(self) -> [u8; 2] {
        match self {
            Variant::Pic18F25K20 => [0x60, 0x20],
            Variant::Pic18F2455 => [0x60, 0x12],
        }
    }

    /// Access-Bank low boundary (inclusive upper limit of the
    /// "low" half).  An `a=0` instruction operand `f` with
    /// `f < 0x60` resolves directly to RAM byte `f`; otherwise
    /// it resolves to SFR byte `0xF00 | f` on this variant.
    pub const fn access_bank_low_high(self) -> u8 {
        // Both K20 and 2455 use the same 0x60 boundary because
        // the 2455's USB SFRs occupy 0xF66-0xF7F and the access-
        // bank-high half starts at 0xF60 anyway.
        0x60
    }
}

/// 12-bit data-memory address.  Wraps a `u16` so the upper 4 bits
/// stay 0 — a runtime invariant the addressing arithmetic relies
/// on.  Constructed via [`Address::from_raw`] which panics on out-
/// of-range input (intentional: a value > 0x0FFF can only be a
/// caller bug, never untrusted firmware input).
#[derive(Copy, Clone, Eq, PartialEq, Debug, Hash, Ord, PartialOrd)]
pub struct Address(u16);

impl Address {
    /// Construct from a 12-bit raw value.  Panics if `value > 0x0FFF`.
    pub const fn from_raw(value: u16) -> Self {
        assert!(value <= 0x0FFF, "data-memory address must fit in 12 bits");
        Address(value)
    }

    /// Construct from a `(bank, offset)` pair.  Both must fit
    /// within their nibble; panics otherwise.
    pub const fn from_bank_offset(bank: u8, offset: u8) -> Self {
        assert!(bank < 16, "PIC18 has 16 banks");
        Address(((bank as u16) << 8) | (offset as u16))
    }

    /// Return the raw 12-bit value.
    pub const fn as_u16(self) -> u16 {
        self.0
    }

    /// Return the bank nibble (0..=15).
    pub const fn bank(self) -> u8 {
        ((self.0 >> 8) & 0x0F) as u8
    }

    /// Return the in-bank offset (0..=255).
    pub const fn offset(self) -> u8 {
        (self.0 & 0xFF) as u8
    }

    /// True if the address falls inside the top-of-bank-15 SFR
    /// window `0xF60..=0xFFF`.  P1.2's instruction interpreter
    /// uses this to decide whether to dispatch via the per-SFR
    /// read/write hooks (added in P2) or read the raw RAM byte.
    pub const fn is_sfr(self) -> bool {
        self.0 >= 0xF60 // && self.0 <= 0x0FFF, guaranteed by from_raw
    }
}

/// PIC18 data memory: contiguous 4 KiB backing array plus
/// addressing arithmetic.  Per-variant SFR side effects are wired
/// in via the peripheral modules (P2); this struct is just the
/// raw bytes.
#[derive(Clone)]
pub struct Memory {
    variant: Variant,
    bytes: Box<[u8]>,
}

impl Memory {
    /// New zero-initialised memory.  POR values for individual
    /// SFRs are written by [`crate::core::Core::reset`] after
    /// the peripheral set is constructed (P1.6).
    pub fn new(variant: Variant) -> Self {
        let bytes = vec![0u8; variant.data_memory_bytes()].into_boxed_slice();
        Memory { variant, bytes }
    }

    /// Variant this memory was constructed for.
    pub const fn variant(&self) -> Variant {
        self.variant
    }

    /// Resolve an instruction operand into a physical address.
    ///
    /// `f` is the 8-bit file-register field of the operand.
    /// `a_bit` is the operand's `a` bit:
    ///
    ///   * `a = false` (Access Bank semantics):
    ///     - `f < 0x60` → address `0x000 | f` (low Access RAM).
    ///     - `f >= 0x60` → address `0xF00 | f` (top-of-bank-15 SFR).
    ///   * `a = true` (BSR-selected): address `(bsr << 8) | f`.
    ///
    /// `bsr` is consulted only when `a_bit` is true.
    pub const fn resolve(&self, f: u8, a_bit: bool, bsr: u8) -> Address {
        if a_bit {
            Address::from_bank_offset(bsr & 0x0F, f)
        } else if f < self.variant.access_bank_low_high() {
            Address::from_bank_offset(0, f)
        } else {
            Address::from_bank_offset(15, f)
        }
    }

    /// Read one byte without dispatching to any SFR side-effect
    /// hook.  P2 wraps this with `read_byte_through_peripherals`.
    pub fn read_raw(&self, addr: Address) -> u8 {
        self.bytes[addr.0 as usize]
    }

    /// Write one byte without dispatching to any SFR side-effect
    /// hook.  P2 wraps this with `write_byte_through_peripherals`.
    pub fn write_raw(&mut self, addr: Address, value: u8) {
        self.bytes[addr.0 as usize] = value;
    }

    /// Borrow the entire backing array (read-only).  Used by the
    /// snapshot-style ground-truth diff in P1.8.
    pub fn as_slice(&self) -> &[u8] {
        &self.bytes
    }

    /// Borrow the entire backing array mutably.  Reserved for the
    /// reset path (P1.6) and the peripheral SFR-write hooks (P2);
    /// general code should go through `write_raw` so callers can be
    /// audited.
    pub(crate) fn as_mut_slice(&mut self) -> &mut [u8] {
        &mut self.bytes
    }
}

/// Access-Bank-specific helpers and dedicated boundary tests.
///
/// Most call sites just use [`Memory::resolve`] with the `a` bit
/// taken from the decoded instruction; this submodule exposes a
/// single-purpose helper for the `a=0` path so peripheral code
/// reading an SFR by name (`mem.access_bank(0xB8)` for BAUDCON,
/// say) doesn't have to remember to pass `a=false, bsr=anything`.
///
/// The tests live under `memory::access_bank::tests::*` so the
/// `cargo test --release memory::access_bank::tests` filter
/// (P1.3 verify gate) picks them up.
pub mod access_bank {
    use super::{Address, Memory};

    impl Memory {
        /// Resolve an Access-Bank (`a=0`) operand `f` directly,
        /// without consulting BSR.  Equivalent to
        /// `self.resolve(f, false, _)` but communicates intent
        /// at the call site.
        ///
        /// * `f < 0x60` → Address `0x000 | f` (Access RAM low).
        /// * `f >= 0x60` → Address `0xF00 | f` (top-of-bank-15
        ///   SFR window).
        pub const fn access_bank(&self, f: u8) -> Address {
            self.resolve(f, false, 0)
        }
    }

    #[cfg(test)]
    mod tests {
        use super::super::{Address, Memory, Variant};

        // ----- Helpers -----

        fn k20_mem() -> Memory {
            Memory::new(Variant::Pic18F25K20)
        }

        fn p2455_mem() -> Memory {
            Memory::new(Variant::Pic18F2455)
        }

        // ----- Access Bank low half (`f < 0x60` → bank 0) -----

        #[test]
        fn access_bank_low_at_zero_routes_to_bank0() {
            let m = k20_mem();
            assert_eq!(m.access_bank(0x00), Address::from_raw(0x000));
        }

        #[test]
        fn access_bank_low_at_5f_routes_to_bank0() {
            // f = 0x5F is the *highest* low-half address (the
            // boundary minus one).  Stays in bank 0.
            let m = p2455_mem();
            assert_eq!(m.access_bank(0x5F), Address::from_raw(0x05F));
        }

        // ----- Access Bank high half (`f >= 0x60` → SFR area) -----

        #[test]
        fn access_bank_high_at_60_routes_to_sfr() {
            // f = 0x60 is the *lowest* high-half address.  PIC18
            // routes it to 0xF60 — first byte of the SFR window.
            let m = k20_mem();
            assert_eq!(m.access_bank(0x60), Address::from_raw(0xF60));
        }

        #[test]
        fn access_bank_high_at_b8_routes_to_baudcon() {
            // f = 0xB8 is BAUDCON on both 2455 and K20 (DS39632E
            // Table 5-1 data row + DS41303G; spec §11b
            // resolution).  V3.2 MAIN's `movwf BAUDCON, ACCESS`
            // (opcode 0x6EB8) lands here.
            let m = p2455_mem();
            assert_eq!(m.access_bank(0xB8), Address::from_raw(0xFB8));
            // Same on K20 (CONTROL).
            let m = k20_mem();
            assert_eq!(m.access_bank(0xB8), Address::from_raw(0xFB8));
        }

        #[test]
        fn access_bank_high_at_ff_routes_to_top_of_bank15() {
            let m = k20_mem();
            assert_eq!(m.access_bank(0xFF), Address::from_raw(0xFFF));
        }

        // ----- Resolved address must classify correctly -----

        #[test]
        fn access_bank_high_addresses_are_sfr_classed() {
            let m = p2455_mem();
            assert!(m.access_bank(0x60).is_sfr());
            assert!(m.access_bank(0xB8).is_sfr());
            assert!(m.access_bank(0xFF).is_sfr());
        }

        #[test]
        fn access_bank_low_addresses_are_not_sfr_classed() {
            let m = p2455_mem();
            assert!(!m.access_bank(0x00).is_sfr());
            assert!(!m.access_bank(0x05F).is_sfr());
        }

        // ----- BSR-selected (`a=1`) path through Memory::resolve -----

        #[test]
        fn banked_uses_full_bsr() {
            let m = k20_mem();
            assert_eq!(m.resolve(0x42, true, 0x0F).as_u16(), 0xF42);
            assert_eq!(m.resolve(0x10, true, 0x07).as_u16(), 0x710);
            assert_eq!(m.resolve(0x00, true, 0x00).as_u16(), 0x000);
        }

        #[test]
        fn banked_masks_bsr_high_nibble() {
            // PIC18 BSR is 4 bits in real silicon; the upper 4
            // bits of any value passed in must be ignored so the
            // simulator doesn't accidentally accept `bsr=0x1F`
            // and resolve into bank 31 (which doesn't exist).
            let m = p2455_mem();
            assert_eq!(m.resolve(0x10, true, 0xF7).as_u16(), 0x710);
            assert_eq!(m.resolve(0x10, true, 0x47).as_u16(), 0x710);
        }

        #[test]
        fn banked_low_f_does_not_alias_to_bank0() {
            // Under `a=1`, even `f < 0x60` consults BSR and
            // routes to `(BSR << 8) | f`, NOT bank 0.  This is
            // the distinguishing case between Access-Bank and
            // banked addressing.
            let m = k20_mem();
            assert_eq!(m.resolve(0x05, true, 0x03).as_u16(), 0x305);
        }

        #[test]
        fn banked_high_f_does_not_alias_to_sfr() {
            // Symmetrically, `a=1, f >= 0x60` resolves through
            // BSR, so f=0xB8 with BSR=0x07 lands at 0x7B8 — NOT
            // 0xFB8 (BAUDCON).  This is one of the most common
            // PIC18 "I forgot the access bank" bugs in firmware.
            let m = p2455_mem();
            assert_eq!(m.resolve(0xB8, true, 0x07).as_u16(), 0x7B8);
        }

        // ----- The two routes can be told apart at the same `f` -----

        #[test]
        fn same_f_different_a_route_differently() {
            let m = k20_mem();
            // f = 0xB8.
            // a=0 (Access)  → 0xFB8 (BAUDCON / SFR window).
            // a=1 (Banked)  → (BSR << 8) | 0xB8.
            assert_eq!(m.access_bank(0xB8).as_u16(), 0xFB8);
            assert_eq!(m.resolve(0xB8, true, 0x05).as_u16(), 0x5B8);
            assert_ne!(
                m.access_bank(0xB8).as_u16(),
                m.resolve(0xB8, true, 0x05).as_u16(),
            );
        }

        #[test]
        fn variant_independent_routing() {
            // Both PIC18F25K20 and PIC18F2455 use the same 0x60
            // Access-Bank split (spec §6 + DS39632E §5.3 +
            // DS41303G §5.3).  The 2455 has USB SFRs at
            // 0xF66-0xF7F, but those are a property of the SFR
            // map, not of the addressing arithmetic.
            for variant in [Variant::Pic18F25K20, Variant::Pic18F2455] {
                let m = Memory::new(variant);
                assert_eq!(m.access_bank(0x5F).as_u16(), 0x05F);
                assert_eq!(m.access_bank(0x60).as_u16(), 0xF60);
                assert_eq!(m.access_bank(0xB8).as_u16(), 0xFB8);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn variant_data_memory_size() {
        assert_eq!(Variant::Pic18F25K20.data_memory_bytes(), 4096);
        assert_eq!(Variant::Pic18F2455.data_memory_bytes(), 4096);
    }

    #[test]
    fn variant_access_bank_split_is_0x60_for_both() {
        // Spec §6 + DS39632E §5.3: both variants share the 0x60
        // low/high boundary even though the 2455 has USB SFRs
        // tucked between 0xF66 and 0xF7F.
        assert_eq!(Variant::Pic18F25K20.access_bank_low_high(), 0x60);
        assert_eq!(Variant::Pic18F2455.access_bank_low_high(), 0x60);
    }

    #[test]
    fn address_arithmetic_round_trips() {
        let a = Address::from_bank_offset(0xC, 0x42);
        assert_eq!(a.as_u16(), 0x0C42);
        assert_eq!(a.bank(), 0xC);
        assert_eq!(a.offset(), 0x42);
    }

    #[test]
    fn resolve_access_bank_low_routes_to_bank0() {
        // f = 0x05, a = 0  →  0x005 (Access Bank low)
        let mem = Memory::new(Variant::Pic18F2455);
        assert_eq!(mem.resolve(0x05, false, 0xFF).as_u16(), 0x005);
    }

    #[test]
    fn resolve_access_bank_high_routes_to_bank15_sfr() {
        // f = 0xB8, a = 0  →  0xFB8 (BAUDCON on the 2455 / K20 per
        // spec §11b).
        let mem = Memory::new(Variant::Pic18F2455);
        assert_eq!(mem.resolve(0xB8, false, 0xFF).as_u16(), 0xFB8);
    }

    #[test]
    fn resolve_banked_uses_bsr() {
        // f = 0x42, a = 1, bsr = 0x07  →  0x742
        let mem = Memory::new(Variant::Pic18F25K20);
        assert_eq!(mem.resolve(0x42, true, 0x07).as_u16(), 0x742);
    }

    #[test]
    fn resolve_banked_masks_high_nibble_of_bsr() {
        // BSR is only 4 bits on PIC18; high nibble is ignored.
        let mem = Memory::new(Variant::Pic18F25K20);
        assert_eq!(mem.resolve(0x10, true, 0xF3).as_u16(), 0x310);
    }

    #[test]
    fn is_sfr_threshold() {
        assert!(!Address::from_raw(0xF5F).is_sfr());
        assert!(Address::from_raw(0xF60).is_sfr());
        assert!(Address::from_raw(0xFB8).is_sfr());
        assert!(Address::from_raw(0xFFF).is_sfr());
    }

    #[test]
    fn read_write_round_trip() {
        let mut mem = Memory::new(Variant::Pic18F25K20);
        mem.write_raw(Address::from_raw(0x123), 0x42);
        assert_eq!(mem.read_raw(Address::from_raw(0x123)), 0x42);
    }
}
