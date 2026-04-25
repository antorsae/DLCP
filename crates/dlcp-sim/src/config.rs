//! PIC18 configuration-words parser.
//!
//! The 14 CONFIG bytes (CONFIG1L through CONFIG7H) live at
//! flash addresses 0x300000-0x30000D.  They control oscillator
//! selection, watchdog enable, brown-out reset, MCLR pin
//! function, code/data protection, stack-overflow reset
//! behaviour, and a few other static device-level flags.
//!
//! References:
//! * DS39632E §22 + Table 22-1, "Configuration Bits and Device
//!   IDs" (PIC18F2455).
//! * DS41303G §23 (PIC18F25K20 — same general layout, bit
//!   assignments differ in places).
//!
//! This module owns the static parsing — taking 14 raw bytes
//! and exposing typed accessors.  It does NOT read the bytes
//! out of program memory itself; the caller (P1.6 reset path
//! and the executor's pre-fetch boot) extracts the 14-byte
//! slice from the hex loader's flash buffer and hands it to
//! [`Config::from_bytes`].
//!
//! ## Coverage scope (P1.7)
//!
//! P1.7 lays the parser surface for the bits the rest of the
//! simulator needs to consult:
//!
//! * `STVREN` (CONFIG4L bit 0) — drives whether stack
//!   overflow / underflow triggers a reset (consumed by P1.6).
//! * `WDTEN` (CONFIG2H bit 0) — hardware watchdog always-on.
//! * `BOREN[1:0]` (CONFIG2L bits 2..1) — brown-out enable mode.
//! * `MCLRE` (CONFIG3H bit 7) — MCLR pin function.
//! * `FOSC[3:0]` (CONFIG1H bits 3..0) — oscillator selector.
//! * `PLLDIV[2:0]` (CONFIG1L bits 2..0) — USB PLL prescaler
//!   (2455 only; ignored on K20).
//! * `CPUDIV[1:0]` (CONFIG1L bits 4..3) — CPU clock divider.
//!
//! Other CONFIG bits (code-protect, write-protect, debug,
//! XINST, etc.) are not consumed by the firmware path that
//! drives this rewrite, so they're parsed-and-stored but not
//! exposed via dedicated accessors.  Adding more accessors is
//! a one-line change when a future peripheral needs them.

#![allow(dead_code, reason = "P1.7 parser; consumed by P1.6 reset path + P2 oscillator/peripheral models")]

/// Number of configuration bytes parsed by this module.  PIC18
/// has 7 16-bit CONFIG words = 14 bytes, sized identically
/// across the 2455 and K20.
pub const CONFIG_BYTES: usize = 14;

/// Flash byte address of CONFIG1L (the first config byte) on
/// both PIC18 variants.  The full CONFIG region runs to
/// `CONFIG_BASE + CONFIG_BYTES - 1` = 0x30000D.  The hex
/// loader (out of scope for P1.7) is responsible for placing
/// CONFIG bytes at this address; this module just consumes a
/// `[u8; CONFIG_BYTES]` slice.
pub const CONFIG_BASE: u32 = 0x0030_0000;

/// Brown-out enable encoding (CONFIG2L bits 2..1).
#[derive(Copy, Clone, Eq, PartialEq, Debug, Hash)]
pub enum BorenMode {
    /// `00` — BOR disabled in hardware AND software.
    Disabled,
    /// `01` — BOR controlled by SBOREN (RCON bit 6); software
    /// can enable/disable at runtime.
    SoftwareControlled,
    /// `10` — BOR enabled in hardware in run mode, disabled
    /// in Idle/Sleep.
    HardwareRunOnly,
    /// `11` — BOR enabled in hardware always.
    HardwareAlways,
}

impl BorenMode {
    pub const fn from_bits(bits: u8) -> Self {
        match bits & 0b11 {
            0 => BorenMode::Disabled,
            1 => BorenMode::SoftwareControlled,
            2 => BorenMode::HardwareRunOnly,
            3 => BorenMode::HardwareAlways,
            _ => unreachable!(),
        }
    }
}

/// Oscillator selection (CONFIG1H FOSC[3:0]).  Lists every
/// encoding documented in DS39632E Table 22-3.  Reserved
/// encodings collapse to `Reserved(bits)` so the executor
/// can fail loudly rather than silently picking a default.
#[derive(Copy, Clone, Eq, PartialEq, Debug, Hash)]
pub enum FoscMode {
    /// `0000` — XT.
    XT,
    /// `0001` — XT, USB clock from primary OSC ÷ 1.  Used by
    /// CONTROL.
    XTPLL,
    /// `0010` — EC.
    EC,
    /// `0011` — EC, USB clock from primary OSC ÷ 1.  Used by
    /// MAIN (16 MHz crystal × ECPIO setting + 96 MHz USB PLL).
    ECPIO,
    /// `0100` — HS.
    HS,
    /// `0101` — HS, USB clock from primary OSC.
    HSPLL,
    /// `0110` — RC.
    RC,
    /// `0111` — RC IO.
    RCIO,
    /// `1000` — INTRC.
    Intrc,
    /// `1001` — INTRC IO with SOSC oscillator on T1OSC.
    IntrcIo,
    /// Anything not in the documented table.
    Reserved(u8),
}

impl FoscMode {
    pub const fn from_bits(bits: u8) -> Self {
        match bits & 0xF {
            0b0000 => FoscMode::XT,
            0b0001 => FoscMode::XTPLL,
            0b0010 => FoscMode::EC,
            0b0011 => FoscMode::ECPIO,
            0b0100 => FoscMode::HS,
            0b0101 => FoscMode::HSPLL,
            0b0110 => FoscMode::RC,
            0b0111 => FoscMode::RCIO,
            0b1000 => FoscMode::Intrc,
            0b1001 => FoscMode::IntrcIo,
            other => FoscMode::Reserved(other as u8),
        }
    }
}

/// Parsed view of the 14 CONFIG bytes.
#[derive(Copy, Clone, Eq, PartialEq, Debug)]
pub struct Config {
    raw: [u8; CONFIG_BYTES],
}

impl Config {
    /// Parse the 14 CONFIG bytes.  No validation beyond size —
    /// reserved bit patterns surface through the typed
    /// accessors (e.g. [`Config::fosc`] returns
    /// `FoscMode::Reserved(...)` for undocumented FOSC
    /// encodings).
    pub const fn from_bytes(bytes: [u8; CONFIG_BYTES]) -> Self {
        Config { raw: bytes }
    }

    /// Borrow the raw 14-byte CONFIG region.  Mostly useful
    /// for diagnostics + the snapshot/restore path (P5.1).
    pub const fn raw(&self) -> &[u8; CONFIG_BYTES] {
        &self.raw
    }

    // ------- CONFIG1L (byte 0) -------

    /// PLLDIV[2:0] (CONFIG1L bits 2..0).  USB PLL prescaler
    /// selector on the 2455.  Ignored on K20 (no USB).
    pub const fn plldiv(&self) -> u8 {
        self.raw[0] & 0b0000_0111
    }

    /// CPUDIV[1:0] (CONFIG1L bits 4..3).  CPU clock divider
    /// post the PLL / oscillator selector.
    pub const fn cpudiv(&self) -> u8 {
        (self.raw[0] >> 3) & 0b11
    }

    /// USBDIV (CONFIG1L bit 5) — USB clock source on the 2455.
    pub const fn usbdiv(&self) -> bool {
        (self.raw[0] >> 5) & 1 == 1
    }

    // ------- CONFIG1H (byte 1) -------

    /// FOSC[3:0] (CONFIG1H bits 3..0).
    pub const fn fosc(&self) -> FoscMode {
        FoscMode::from_bits(self.raw[1] & 0xF)
    }

    /// FCMEN (CONFIG1H bit 6) — Fail-Safe Clock Monitor.
    pub const fn fcmen(&self) -> bool {
        (self.raw[1] >> 6) & 1 == 1
    }

    /// IESO (CONFIG1H bit 7) — Internal/External Switchover.
    pub const fn ieso(&self) -> bool {
        (self.raw[1] >> 7) & 1 == 1
    }

    // ------- CONFIG2L (byte 2) -------

    /// PWRTEN (CONFIG2L bit 0) — Power-up Timer enable.
    /// Note: CONFIG2L's PWRTEN is *active-low* in the Microchip
    /// datasheet (PWRTEN# = 0 enables PWRT).  Returning the
    /// raw bit lets the caller apply the polarity it expects.
    pub const fn pwrten_bit(&self) -> bool {
        (self.raw[2] >> 0) & 1 == 1
    }

    /// BOREN[1:0] (CONFIG2L bits 2..1) — Brown-Out Reset
    /// enable mode.
    pub const fn boren(&self) -> BorenMode {
        BorenMode::from_bits((self.raw[2] >> 1) & 0b11)
    }

    /// BORV[1:0] (CONFIG2L bits 4..3) — Brown-Out Reset
    /// voltage selector.
    pub const fn borv(&self) -> u8 {
        (self.raw[2] >> 3) & 0b11
    }

    // ------- CONFIG2H (byte 3) -------

    /// WDTEN (CONFIG2H bit 0) — Watchdog Timer always-on.
    pub const fn wdten(&self) -> bool {
        (self.raw[3] >> 0) & 1 == 1
    }

    /// WDTPS[3:0] (CONFIG2H bits 4..1) — WDT prescaler.
    pub const fn wdtps(&self) -> u8 {
        (self.raw[3] >> 1) & 0xF
    }

    // ------- CONFIG3H (byte 5; CONFIG3L at byte 4 is unused) -------

    /// MCLRE (CONFIG3H bit 7) — MCLR pin enable.
    pub const fn mclre(&self) -> bool {
        (self.raw[5] >> 7) & 1 == 1
    }

    /// LPT1OSC (CONFIG3H bit 2) — Low-Power Timer1 OSC.
    pub const fn lpt1osc(&self) -> bool {
        (self.raw[5] >> 2) & 1 == 1
    }

    /// PBADEN (CONFIG3H bit 1) — PORTB A/D Enable.
    pub const fn pbaden(&self) -> bool {
        (self.raw[5] >> 1) & 1 == 1
    }

    /// CCP2MX (CONFIG3H bit 0) — CCP2 Mux.
    pub const fn ccp2mx(&self) -> bool {
        (self.raw[5] >> 0) & 1 == 1
    }

    // ------- CONFIG4L (byte 6) -------

    /// STVREN (CONFIG4L bit 0) — Stack Overflow / Underflow
    /// Reset Enable.  `true` ⇒ stack-full / stack-underflow
    /// triggers a device reset; `false` ⇒ the latch sets but
    /// no reset fires (the executor in P1.2 just signals to
    /// the operator that something tried to push past 31 / pop
    /// at empty).
    pub const fn stvren(&self) -> bool {
        (self.raw[6] >> 0) & 1 == 1
    }

    /// LVP (CONFIG4L bit 2) — Single-Supply ICSP Enable.
    pub const fn lvp(&self) -> bool {
        (self.raw[6] >> 2) & 1 == 1
    }

    /// XINST (CONFIG4L bit 6) — Extended Instruction Set.
    /// All firmware on this product uses XINST=0 (legacy
    /// PIC18 instruction set).  P1.2's decoder is for the
    /// 75-instruction legacy set; if XINST=1 the decoder
    /// would need extension, so the executor should fail
    /// loudly when it sees this set.
    pub const fn xinst(&self) -> bool {
        (self.raw[6] >> 6) & 1 == 1
    }

    /// DEBUG (CONFIG4L bit 7) — Background-Debug enable.
    pub const fn debug(&self) -> bool {
        (self.raw[6] >> 7) & 1 == 1
    }

    // ------- CONFIG5L/H, CONFIG6L/H, CONFIG7L/H (bytes 8-13) -------
    //
    // Code-protect / write-protect / external-table-read
    // bits.  Not consumed by the firmware path this rewrite
    // is built against; access via `raw()` if needed.
}

#[cfg(test)]
mod tests {
    use super::*;

    /// CONFIG bytes that match the V3.2 MAIN release as
    /// observed in the assembled hex (not a perfect match
    /// — just plausible representative values for the parser
    /// tests).
    const V32_MAIN_LIKE: [u8; CONFIG_BYTES] = [
        // CONFIG1L: PLLDIV=001, CPUDIV=00, USBDIV=0
        0x01,
        // CONFIG1H: FOSC=ECPIO (0011), FCMEN=0, IESO=0
        0x03,
        // CONFIG2L: BOREN=11 (always on), BORV=00, PWRTEN=0
        0b0000_0110,
        // CONFIG2H: WDTEN=0, WDTPS=1111
        0b0001_1110,
        // CONFIG3L (unused on 2455)
        0x00,
        // CONFIG3H: MCLRE=1, LPT1OSC=0, PBADEN=0, CCP2MX=1
        0b1000_0001,
        // CONFIG4L: STVREN=1, LVP=0, XINST=0, DEBUG=1
        0b1000_0001,
        // CONFIG4H (unused)
        0x00,
        // CONFIG5L (no code protect)
        0x0F,
        // CONFIG5H
        0xC0,
        // CONFIG6L
        0x0F,
        // CONFIG6H
        0xE0,
        // CONFIG7L
        0x0F,
        // CONFIG7H
        0x40,
    ];

    fn cfg() -> Config {
        Config::from_bytes(V32_MAIN_LIKE)
    }

    // ------- CONFIG1L -------

    #[test]
    fn plldiv_lifted_from_low_3_bits() {
        assert_eq!(cfg().plldiv(), 0b001);
    }

    #[test]
    fn cpudiv_lifted_from_bits_4_3() {
        let c = Config::from_bytes([0b0001_1000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
        assert_eq!(c.cpudiv(), 0b11);
    }

    #[test]
    fn usbdiv_lifted_from_bit_5() {
        let c = Config::from_bytes([0b0010_0000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
        assert!(c.usbdiv());
        let c = Config::from_bytes([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
        assert!(!c.usbdiv());
    }

    // ------- CONFIG1H FOSC -------

    #[test]
    fn fosc_decodes_each_documented_encoding() {
        let mut c = V32_MAIN_LIKE;
        for (bits, expected) in [
            (0b0000, FoscMode::XT),
            (0b0001, FoscMode::XTPLL),
            (0b0010, FoscMode::EC),
            (0b0011, FoscMode::ECPIO),
            (0b0100, FoscMode::HS),
            (0b0101, FoscMode::HSPLL),
            (0b0110, FoscMode::RC),
            (0b0111, FoscMode::RCIO),
            (0b1000, FoscMode::Intrc),
            (0b1001, FoscMode::IntrcIo),
        ] {
            c[1] = bits;
            assert_eq!(Config::from_bytes(c).fosc(), expected);
        }
    }

    #[test]
    fn fosc_reserved_encoding_surfaces_as_reserved() {
        let mut c = V32_MAIN_LIKE;
        c[1] = 0b1111;
        assert_eq!(Config::from_bytes(c).fosc(), FoscMode::Reserved(0b1111));
    }

    #[test]
    fn fcmen_and_ieso() {
        let c = Config::from_bytes([0, 0b1100_0000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
        assert!(c.fcmen());
        assert!(c.ieso());
        let c = Config::from_bytes([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
        assert!(!c.fcmen());
        assert!(!c.ieso());
    }

    // ------- CONFIG2L BOREN -------

    #[test]
    fn boren_decodes_each_pattern() {
        for (bits, expected) in [
            (0b00, BorenMode::Disabled),
            (0b01, BorenMode::SoftwareControlled),
            (0b10, BorenMode::HardwareRunOnly),
            (0b11, BorenMode::HardwareAlways),
        ] {
            let c = Config::from_bytes([0, 0, bits << 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
            assert_eq!(c.boren(), expected);
        }
    }

    #[test]
    fn borv_and_pwrten() {
        let c = Config::from_bytes([0, 0, 0b0001_1001, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
        // PWRTEN bit 0 = 1; BOREN bits 2..1 = 0b00; BORV bits 4..3 = 0b11.
        assert!(c.pwrten_bit());
        assert_eq!(c.boren(), BorenMode::Disabled);
        assert_eq!(c.borv(), 0b11);
    }

    // ------- CONFIG2H WDT -------

    #[test]
    fn wdten_and_wdtps() {
        let c = Config::from_bytes([0, 0, 0, 0b0001_1111, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
        assert!(c.wdten());
        assert_eq!(c.wdtps(), 0b1111);
    }

    // ------- CONFIG3H -------

    #[test]
    fn mclre_lifted_from_bit_7() {
        let c = Config::from_bytes([0, 0, 0, 0, 0, 0b1000_0000, 0, 0, 0, 0, 0, 0, 0, 0]);
        assert!(c.mclre());
    }

    #[test]
    fn ccp2mx_lifted_from_bit_0() {
        let c = Config::from_bytes([0, 0, 0, 0, 0, 0b0000_0001, 0, 0, 0, 0, 0, 0, 0, 0]);
        assert!(c.ccp2mx());
    }

    // ------- CONFIG4L STVREN / XINST / DEBUG -------

    #[test]
    fn stvren_drives_stack_reset_policy() {
        // STVREN=1 (bit 0 set): stack overflow/underflow triggers reset.
        let mut c = V32_MAIN_LIKE;
        c[6] = 0b0000_0001;
        assert!(Config::from_bytes(c).stvren());
        // STVREN=0: latch only.
        c[6] = 0;
        assert!(!Config::from_bytes(c).stvren());
    }

    #[test]
    fn xinst_disabled_for_v32_like_config() {
        // V3.2 MAIN firmware uses the legacy 75-instruction set,
        // so XINST must be 0.  The reference CONFIG4L value
        // 0b1000_0001 has bit 6 (XINST) clear.
        let c = cfg();
        assert!(!c.xinst());
    }

    #[test]
    fn debug_bit_lifted_from_config4l_bit_7() {
        let c = cfg();
        // Reference CONFIG4L = 0b1000_0001 → DEBUG=1.
        assert!(c.debug());
    }

    // ------- raw / round-trip -------

    #[test]
    fn raw_bytes_round_trip() {
        let c = cfg();
        assert_eq!(c.raw(), &V32_MAIN_LIKE);
    }

    // ------- aggregate sanity test mirroring V3.2-like config -------

    #[test]
    fn v32_like_config_parses_consistently() {
        let c = cfg();
        assert_eq!(c.plldiv(), 0b001);
        assert_eq!(c.cpudiv(), 0b00);
        assert!(!c.usbdiv());
        assert_eq!(c.fosc(), FoscMode::ECPIO);
        assert!(!c.fcmen());
        assert!(!c.ieso());
        assert_eq!(c.boren(), BorenMode::HardwareAlways);
        assert!(!c.wdten());
        assert!(c.mclre());
        assert!(c.stvren());
        assert!(!c.xinst());
    }
}
