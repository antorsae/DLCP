//! PIC18 configuration-words parser.
//!
//! The 14 CONFIG bytes (CONFIG1L through CONFIG7H) live at
//! flash addresses 0x300000-0x30000D.  They control oscillator
//! selection, watchdog enable, brown-out reset, MCLR pin
//! function, code/data protection, stack-overflow reset
//! behaviour, and a few other static device-level flags.
//!
//! References:
//! * DS39632E §25 ("Special Features of the CPU") + §25.1
//!   "Configuration Bits" (Table 25-1 plus Registers 25-1
//!   through 25-13) (PIC18F2455).
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
//! P1.7 exposes typed accessors for every documented bit in
//! CONFIG1L–CONFIG4L (the bits future peripherals actually
//! consult): `PLLDIV`, `CPUDIV`, `USBDIV`, `FOSC`, `FCMEN`,
//! `IESO`, `PWRTEN` (+ polarity-corrected `pwrt_enabled`),
//! `BOREN`, `BORV`, `VREGEN`, `WDTEN`, `WDTPS`, `MCLRE`,
//! `LPT1OSC`, `PBADEN`, `CCP2MX`, `STVREN`, `LVP`, `XINST`,
//! `DEBUG` (raw `debug_bit` + polarity-corrected
//! `debugger_enabled`).
//!
//! CONFIG5..CONFIG7 carry only code-protect / write-protect /
//! external-table-read bits, none of which are consulted by the
//! firmware path this rewrite is built against.  Those bytes
//! are parsed-and-stored (visible through [`Config::raw`]) but
//! have no dedicated accessor; adding one is a one-line change
//! when a future need arises.

#![allow(dead_code, reason = "P1.7 parser; consumed by P1.6 reset path + P2 oscillator/peripheral models")]

use serde::{Deserialize, Serialize};

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
#[derive(Serialize, Deserialize, Copy, Clone, Eq, PartialEq, Debug, Hash)]
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

/// Oscillator selection (CONFIG1H FOSC[3:0]) per DS39632E §25 /
/// Register 25-2.  All 16 four-bit encodings are documented for
/// the PIC18F2455/2550/4455/4550 family — there is no reserved
/// pattern.  Note that for four of the modes (XT, XTPLL, HS,
/// HSPLL) the low bit is "don't care" so two consecutive
/// encodings collapse onto the same mode.
#[derive(Serialize, Deserialize, Copy, Clone, Eq, PartialEq, Debug, Hash)]
pub enum FoscMode {
    /// `000x` — XT crystal/resonator.
    XT,
    /// `001x` — XT crystal/resonator, PLL enabled (XTPLL).
    XTPLL,
    /// `0100` — EC oscillator, port function on RA6 (ECIO).
    ECIO,
    /// `0101` — EC oscillator, CLKO function on RA6 (EC).
    EC,
    /// `0110` — EC oscillator, PLL enabled, port function on
    /// RA6 (ECPIO).  This is the V3.2 MAIN configuration:
    /// CONFIG1H = 0x46 → FOSC = 0b0110.
    ECPIO,
    /// `0111` — EC oscillator, PLL enabled, CLKO function on
    /// RA6 (ECPLL).
    ECPLL,
    /// `1000` — Internal oscillator, port function on RA6,
    /// EC used by USB (INTIO).
    INTIO,
    /// `1001` — Internal oscillator, CLKO function on RA6,
    /// EC used by USB (INTCKO).
    INTCKO,
    /// `1010` — Internal oscillator, XT used by USB (INTXT).
    INTXT,
    /// `1011` — Internal oscillator, HS used by USB (INTHS).
    INTHS,
    /// `110x` — HS oscillator (HS).
    HS,
    /// `111x` — HS oscillator, PLL enabled (HSPLL).
    HSPLL,
}

impl FoscMode {
    pub const fn from_bits(bits: u8) -> Self {
        match bits & 0xF {
            0b0000 | 0b0001 => FoscMode::XT,
            0b0010 | 0b0011 => FoscMode::XTPLL,
            0b0100 => FoscMode::ECIO,
            0b0101 => FoscMode::EC,
            0b0110 => FoscMode::ECPIO,
            0b0111 => FoscMode::ECPLL,
            0b1000 => FoscMode::INTIO,
            0b1001 => FoscMode::INTCKO,
            0b1010 => FoscMode::INTXT,
            0b1011 => FoscMode::INTHS,
            0b1100 | 0b1101 => FoscMode::HS,
            0b1110 | 0b1111 => FoscMode::HSPLL,
            _ => unreachable!(),
        }
    }
}

/// Parsed view of the 14 CONFIG bytes.
#[derive(Serialize, Deserialize, Copy, Clone, Eq, PartialEq, Debug)]
pub struct Config {
    raw: [u8; CONFIG_BYTES],
}

impl Config {
    /// Parse the 14 CONFIG bytes.  No validation beyond size.
    /// Every CONFIG1L–CONFIG4L bit consulted by the firmware
    /// path this rewrite targets is exposed through a typed
    /// accessor; CONFIG5..CONFIG7 (code-/write-/external-table-
    /// protect) is parsed-and-stored but only reachable via
    /// [`Self::raw`] until a future consumer needs it.
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
    /// datasheet (`1` = PWRT disabled, `0` = PWRT enabled).
    /// Returning the raw bit lets the caller apply the polarity
    /// it expects; see [`Self::pwrt_enabled`] for the inverted
    /// view.
    pub const fn pwrten_bit(&self) -> bool {
        (self.raw[2] >> 0) & 1 == 1
    }

    /// `true` when PWRT is enabled (CONFIG2L bit 0 = 0).
    pub const fn pwrt_enabled(&self) -> bool {
        !self.pwrten_bit()
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

    /// VREGEN (CONFIG2L bit 5) — USB Internal Voltage Regulator
    /// Enable.  `true` = USB voltage regulator on; `false` =
    /// off.  Only meaningful on the 2455 (the K20 has no USB).
    pub const fn vregen(&self) -> bool {
        (self.raw[2] >> 5) & 1 == 1
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

    /// DEBUG (CONFIG4L bit 7) — *active-low* Background
    /// Debugger control.  Per DS39632E §25 / Register 25-7,
    /// `1` = background debugger DISABLED (RB6/RB7 free as
    /// general-purpose I/O); `0` = debugger ENABLED (RB6/RB7
    /// dedicated to ICD).  Production firmware ships with
    /// DEBUG=1 (debugger off).  Returns the raw bit; use
    /// [`Self::debugger_enabled`] for the polarity-corrected
    /// view.
    pub const fn debug_bit(&self) -> bool {
        (self.raw[6] >> 7) & 1 == 1
    }

    /// `true` when the on-chip background debugger is enabled
    /// (CONFIG4L bit 7 = 0).
    pub const fn debugger_enabled(&self) -> bool {
        !self.debug_bit()
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

    /// Exact CONFIG bytes the V3.2 MAIN release assembles
    /// (`src/dlcp_fw/asm/dlcp_main_v32.asm`, `__CONFIG`
    /// directives at lines 161-172).  This is the canonical
    /// reference — keeping the test vector in lock-step with
    /// the deployed firmware catches FOSC / STVREN / DEBUG /
    /// MCLRE polarity bugs immediately.
    const V32_MAIN: [u8; CONFIG_BYTES] = [
        0x3A, // CONFIG1L: PLLDIV=010, CPUDIV=11, USBDIV=1
        0x46, // CONFIG1H: FOSC=ECPIO (0110), FCMEN=1, IESO=0
        0x3E, // CONFIG2L: PWRTEN=0, BOREN=11, BORV=11, VREGEN=1
        0x1E, // CONFIG2H: WDTEN=0, WDTPS=1111
        0x00, // CONFIG3L (unused on 2455)
        0x00, // CONFIG3H: MCLRE=0, LPT1OSC=0, PBADEN=0, CCP2MX=0
        0x80, // CONFIG4L: DEBUG=1 (off), XINST=0, LVP=0, STVREN=0
        0x00, // CONFIG4H (unused)
        0x0F, // CONFIG5L (no code protect)
        0xC0, // CONFIG5H
        0x0F, // CONFIG6L
        0xA0, // CONFIG6H
        0x0F, // CONFIG7L
        0x40, // CONFIG7H
    ];

    fn cfg() -> Config {
        Config::from_bytes(V32_MAIN)
    }

    // ------- CONFIG1L -------

    #[test]
    fn plldiv_lifted_from_low_3_bits() {
        // V3.2 MAIN: CONFIG1L bits 2..0 = 010.
        assert_eq!(cfg().plldiv(), 0b010);
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
        let mut c = V32_MAIN;
        // Per DS39632E §25 / Register 25-2.  All 16 four-bit
        // encodings are documented; XT / XTPLL / HS / HSPLL
        // collapse pairs of consecutive encodings.
        for (bits, expected) in [
            (0b0000, FoscMode::XT),
            (0b0001, FoscMode::XT),
            (0b0010, FoscMode::XTPLL),
            (0b0011, FoscMode::XTPLL),
            (0b0100, FoscMode::ECIO),
            (0b0101, FoscMode::EC),
            (0b0110, FoscMode::ECPIO),
            (0b0111, FoscMode::ECPLL),
            (0b1000, FoscMode::INTIO),
            (0b1001, FoscMode::INTCKO),
            (0b1010, FoscMode::INTXT),
            (0b1011, FoscMode::INTHS),
            (0b1100, FoscMode::HS),
            (0b1101, FoscMode::HS),
            (0b1110, FoscMode::HSPLL),
            (0b1111, FoscMode::HSPLL),
        ] {
            c[1] = bits;
            assert_eq!(Config::from_bytes(c).fosc(), expected);
        }
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
        // PWRTEN bit 0 = 1 (active-low ⇒ PWRT disabled);
        // BOREN bits 2..1 = 0b00; BORV bits 4..3 = 0b11.
        assert!(c.pwrten_bit());
        assert!(!c.pwrt_enabled());
        assert_eq!(c.boren(), BorenMode::Disabled);
        assert_eq!(c.borv(), 0b11);
    }

    #[test]
    fn vregen_lifted_from_config2l_bit_5() {
        let on = Config::from_bytes([0, 0, 0b0010_0000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
        let off = Config::from_bytes([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
        assert!(on.vregen());
        assert!(!off.vregen());
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
        let mut c = V32_MAIN;
        c[6] = 0b0000_0001;
        assert!(Config::from_bytes(c).stvren());
        // STVREN=0: latch only.
        c[6] = 0;
        assert!(!Config::from_bytes(c).stvren());
    }

    #[test]
    fn xinst_disabled_for_v32_main() {
        // V3.2 MAIN firmware uses the legacy 75-instruction set,
        // so XINST must be 0.  CONFIG4L = 0x80 has bit 6 clear.
        assert!(!cfg().xinst());
    }

    #[test]
    fn debug_bit_polarity_per_datasheet() {
        // V3.2 MAIN: CONFIG4L = 0x80 → bit 7 (DEBUG) = 1, which
        // per DS39632E means the on-chip debugger is *disabled*.
        let c = cfg();
        assert!(c.debug_bit(), "raw DEBUG bit is set in V3.2 MAIN");
        assert!(!c.debugger_enabled(), "DEBUG=1 ⇒ debugger off");

        // Flip CONFIG4L bit 7 to 0 and confirm the polarity-corrected
        // accessor flips with it.
        let mut bytes = V32_MAIN;
        bytes[6] &= 0x7F;
        let c = Config::from_bytes(bytes);
        assert!(!c.debug_bit());
        assert!(c.debugger_enabled());
    }

    // ------- raw / round-trip -------

    #[test]
    fn raw_bytes_round_trip() {
        let c = cfg();
        assert_eq!(c.raw(), &V32_MAIN);
    }

    // ------- aggregate sanity test mirroring V3.2 config -------

    #[test]
    fn v32_main_config_parses_consistently() {
        // Cross-check every accessor against the canonical V3.2
        // MAIN bytes.  This is the parser's "real-firmware" gate
        // — if the bit-shift math drifts from DS39632E, this test
        // breaks first.
        let c = cfg();
        assert_eq!(c.plldiv(), 0b010);
        assert_eq!(c.cpudiv(), 0b11);
        assert!(c.usbdiv());
        assert_eq!(c.fosc(), FoscMode::ECPIO);
        assert!(c.fcmen());
        assert!(!c.ieso());
        assert!(c.pwrt_enabled());
        assert_eq!(c.boren(), BorenMode::HardwareAlways);
        assert_eq!(c.borv(), 0b11);
        assert!(c.vregen());
        assert!(!c.wdten());
        assert_eq!(c.wdtps(), 0b1111);
        assert!(!c.mclre());
        assert!(!c.lpt1osc());
        assert!(!c.pbaden());
        assert!(!c.ccp2mx());
        assert!(!c.stvren(), "V3.2 MAIN ships with stack-reset disabled");
        assert!(!c.lvp());
        assert!(!c.xinst());
        assert!(c.debug_bit(), "raw bit is set");
        assert!(!c.debugger_enabled(), "polarity-corrected: debugger off");
    }
}
