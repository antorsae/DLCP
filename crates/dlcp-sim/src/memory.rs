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

    /// Program (flash) memory size in bytes.  K20 = 32 KiB,
    /// 2455 = 24 KiB but the bootloader window pushes the user
    /// flash up to the full 24 KiB on this product.  P1 stores
    /// the program memory at full-32-KiB capacity for both
    /// variants and lets the config-bit parser (P1.7) bound the
    /// usable region; this avoids special-casing the variant
    /// during instruction fetch.
    pub const fn program_memory_bytes(self) -> usize {
        match self {
            Variant::Pic18F25K20 => 32 * 1024,
            Variant::Pic18F2455 => 32 * 1024,
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
