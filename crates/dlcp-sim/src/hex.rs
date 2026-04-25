//! Intel HEX loader for PIC18 firmware images.
//!
//! Parses the Intel HEX records (types `00` data, `01` EOF,
//! `04` extended-linear-address) emitted by `gpasm` /
//! Microchip `MPASM` and routes the bytes into the four
//! PIC18 memory windows that may appear in a deployed
//! release:
//!
//! | Window  | Byte range                  | Default fill | Notes                                                            |
//! |---------|-----------------------------|--------------|------------------------------------------------------------------|
//! | flash   | `0x000000..0x008000`        | `0xFF`       | 32 KiB on PIC18F25K20 (full); 24 KiB used on PIC18F2455 (top 8 KiB unimplemented) |
//! | user_id | `0x200000..0x200008`        | `0xFF`       | 8-byte application-defined ID                                    |
//! | config  | `0x300000..0x30000E`        | `0xFF`       | 14 CONFIG bytes (parsed by [`crate::config`])                    |
//! | eeprom  | `0xF00000..0xF00100`        | `0xFF`       | 256-byte data EEPROM                                             |
//!
//! `DEVID` at `0x3FFFFE..0x400000` is silicon-only and
//! never appears in a released hex; if a record targets
//! it, the loader returns
//! [`HexLoadError::DeviceIdRecord`] rather than silently
//! discarding.
//!
//! Reference: Intel hexadecimal object file format
//! specification (Microchip TB016) + DS39632E §5
//! (PIC18F2455 program-memory map) and DS41303G §5
//! (PIC18F25K20 program-memory map).

#![allow(dead_code, reason = "P1.8a hex loader; consumed by P1.8b executor + P1.8d/e parity tests")]

use std::fmt;
use std::path::Path;

/// Maximum on-die program memory across the two variants
/// this simulator targets — 32 KiB on the K20 and 24 KiB on
/// the 2455.  Sizing the buffer to the larger variant keeps
/// the loader variant-agnostic; the executor enforces
/// per-variant flash limits at instruction-fetch time.
pub const FLASH_BYTES: usize = 0x8000;

/// User ID memory window length.  Same on both variants.
pub const USER_ID_BYTES: usize = 8;

/// CONFIG region length.  Same on both variants (7 16-bit
/// words = 14 bytes).
pub const CONFIG_BYTES: usize = 14;

/// Data EEPROM length.  256 bytes on both variants.
pub const EEPROM_BYTES: usize = 256;

pub const FLASH_BASE: u32 = 0x0000_0000;
pub const USER_ID_BASE: u32 = 0x0020_0000;
pub const CONFIG_BASE: u32 = 0x0030_0000;
pub const DEVID_BASE: u32 = 0x003F_FFFE;
pub const EEPROM_BASE: u32 = 0x00F0_0000;

/// Loaded HEX image, with each PIC18 memory window broken
/// out separately.  Default fill is `0xFF` (PIC18 erased
/// state).
#[derive(Debug)]
pub struct HexImage {
    pub flash: Box<[u8; FLASH_BYTES]>,
    pub user_id: [u8; USER_ID_BYTES],
    pub config: [u8; CONFIG_BYTES],
    pub eeprom: [u8; EEPROM_BYTES],
}

impl HexImage {
    /// Empty image — every byte set to the PIC18 erased
    /// value (`0xFF`).
    pub fn new() -> Self {
        Self {
            flash: Box::new([0xFF; FLASH_BYTES]),
            user_id: [0xFF; USER_ID_BYTES],
            config: [0xFF; CONFIG_BYTES],
            eeprom: [0xFF; EEPROM_BYTES],
        }
    }

    /// Parse an Intel HEX text blob and route bytes into
    /// the four windows.  Strict: missing EOF, records
    /// after EOF, bad checksums, unknown record types,
    /// out-of-range addresses, and DEVID-targeting
    /// records all surface as errors.
    pub fn from_hex_str(text: &str) -> Result<Self, HexLoadError> {
        let mut image = Self::new();
        let mut ela: u32 = 0;
        let mut saw_eof = false;

        for (idx, raw_line) in text.lines().enumerate() {
            let line_no = idx + 1;
            let line = raw_line.trim_end_matches(['\r', '\n', ' ', '\t']);
            if line.is_empty() {
                continue;
            }
            if saw_eof {
                return Err(HexLoadError::RecordsAfterEof { line: line_no });
            }

            let rec = parse_record(line, line_no)?;
            match rec.kind {
                0x00 => {
                    let base = ela | rec.address as u32;
                    let len = rec.data.len();
                    for (i, &b) in rec.data.iter().enumerate() {
                        // Defense-in-depth against a future window
                        // change that allows write_byte to accept
                        // addresses close to u32::MAX: with the
                        // current windows (highest end is 0xF00100)
                        // write_byte already rejects every address
                        // past 0xF000FF, so byte 0 of an out-of-
                        // range record errors out before the loop
                        // can reach an `i` that would overflow.  The
                        // cost of `checked_add` is one branch per
                        // byte; keep it.
                        let addr = base.checked_add(i as u32).ok_or(
                            HexLoadError::AddressOutOfRange {
                                line: line_no,
                                address: u32::MAX,
                                length: len as u8,
                            },
                        )?;
                        image.write_byte(addr, b, line_no, len)?;
                    }
                }
                0x01 => {
                    if !rec.data.is_empty() {
                        return Err(HexLoadError::EofWithPayload { line: line_no });
                    }
                    if rec.address != 0 {
                        return Err(HexLoadError::BadControlRecordAddress {
                            line: line_no,
                            kind: 0x01,
                            address: rec.address,
                        });
                    }
                    saw_eof = true;
                }
                0x04 => {
                    if rec.data.len() != 2 {
                        return Err(HexLoadError::BadElaLength {
                            line: line_no,
                            len: rec.data.len() as u8,
                        });
                    }
                    if rec.address != 0 {
                        return Err(HexLoadError::BadControlRecordAddress {
                            line: line_no,
                            kind: 0x04,
                            address: rec.address,
                        });
                    }
                    ela = ((rec.data[0] as u32) << 24) | ((rec.data[1] as u32) << 16);
                }
                kind => {
                    return Err(HexLoadError::UnknownRecordType {
                        line: line_no,
                        kind,
                    });
                }
            }
        }

        if !saw_eof {
            return Err(HexLoadError::MissingEof);
        }
        Ok(image)
    }

    /// Convenience wrapper over [`Self::from_hex_str`] that
    /// reads a HEX file from disk.
    pub fn from_hex_path<P: AsRef<Path>>(path: P) -> Result<Self, HexLoadError> {
        let text = std::fs::read_to_string(path.as_ref()).map_err(|e| HexLoadError::Io {
            kind: e.kind(),
            path: path.as_ref().display().to_string(),
        })?;
        Self::from_hex_str(&text)
    }

    fn write_byte(
        &mut self,
        addr: u32,
        byte: u8,
        line: usize,
        record_len: usize,
    ) -> Result<(), HexLoadError> {
        if addr < FLASH_BASE + FLASH_BYTES as u32 {
            self.flash[addr as usize] = byte;
        } else if (USER_ID_BASE..USER_ID_BASE + USER_ID_BYTES as u32).contains(&addr) {
            self.user_id[(addr - USER_ID_BASE) as usize] = byte;
        } else if (CONFIG_BASE..CONFIG_BASE + CONFIG_BYTES as u32).contains(&addr) {
            self.config[(addr - CONFIG_BASE) as usize] = byte;
        } else if (DEVID_BASE..DEVID_BASE + 2).contains(&addr) {
            return Err(HexLoadError::DeviceIdRecord {
                line,
                address: addr,
            });
        } else if (EEPROM_BASE..EEPROM_BASE + EEPROM_BYTES as u32).contains(&addr) {
            self.eeprom[(addr - EEPROM_BASE) as usize] = byte;
        } else {
            return Err(HexLoadError::AddressOutOfRange {
                line,
                address: addr,
                length: record_len as u8,
            });
        }
        Ok(())
    }
}

impl Default for HexImage {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Debug)]
pub enum HexLoadError {
    /// Line did not start with `:`.
    BadStartChar { line: usize },
    /// A character outside `[0-9a-fA-F]` appeared in the
    /// hex body.  `byte_offset` is into the body (after
    /// the leading `:`).
    BadHexDigit { line: usize, byte_offset: usize },
    /// Hex body had an odd number of nibbles.
    OddByteCount { line: usize },
    /// Body shorter than the minimum record size (10
    /// nibbles = LL + AAAA + TT + CC).
    ShortRecord { line: usize, body_len: usize },
    /// LL field disagreed with the actual data byte count
    /// (record total = LL + 5).
    ByteCountMismatch {
        line: usize,
        declared: u8,
        actual: usize,
    },
    /// Record-byte sum modulo 256 was non-zero.
    BadChecksum {
        line: usize,
        computed: u8,
        found: u8,
    },
    /// Record type other than 00/01/04.
    UnknownRecordType { line: usize, kind: u8 },
    /// Type-04 (ELA) record with a payload that is not
    /// exactly 2 bytes.
    BadElaLength { line: usize, len: u8 },
    /// Type-01 (EOF) record with a non-empty payload.
    EofWithPayload { line: usize },
    /// Type-01 (EOF) or type-04 (ELA) control record with a
    /// non-zero address field — the Intel HEX spec requires
    /// `0x0000` for both, so a non-zero value points at a
    /// corrupted hex.
    BadControlRecordAddress {
        line: usize,
        kind: u8,
        address: u16,
    },
    /// Saw another record after the EOF record.
    RecordsAfterEof { line: usize },
    /// Reached end of input without an EOF record.
    MissingEof,
    /// A data byte targeted an address outside any of the
    /// known PIC18 windows (flash / user_id / CONFIG /
    /// EEPROM / DEVID).
    AddressOutOfRange {
        line: usize,
        address: u32,
        length: u8,
    },
    /// A data byte targeted the silicon-only DEVID region
    /// at `0x3FFFFE..0x400000` — DEVID is read-only and
    /// never legitimately appears in a released hex.
    DeviceIdRecord { line: usize, address: u32 },
    /// `read_to_string` failed when called via
    /// [`HexImage::from_hex_path`].
    Io {
        kind: std::io::ErrorKind,
        path: String,
    },
}

impl fmt::Display for HexLoadError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::BadStartChar { line } => {
                write!(f, "line {line}: record must start with ':'")
            }
            Self::BadHexDigit { line, byte_offset } => write!(
                f,
                "line {line}: invalid hex digit at body offset {byte_offset}"
            ),
            Self::OddByteCount { line } => {
                write!(f, "line {line}: hex body has an odd number of nibbles")
            }
            Self::ShortRecord { line, body_len } => write!(
                f,
                "line {line}: record too short (got {body_len} nibbles, need at least 10)"
            ),
            Self::ByteCountMismatch {
                line,
                declared,
                actual,
            } => write!(
                f,
                "line {line}: LL field declared {declared} data bytes but the record holds {actual} total bytes (expected {})",
                *declared as usize + 5
            ),
            Self::BadChecksum {
                line,
                computed,
                found,
            } => write!(
                f,
                "line {line}: checksum mismatch (record claims 0x{found:02X}, computed 0x{computed:02X})"
            ),
            Self::UnknownRecordType { line, kind } => write!(
                f,
                "line {line}: unknown record type 0x{kind:02X} (loader supports 00 / 01 / 04 only)"
            ),
            Self::BadElaLength { line, len } => write!(
                f,
                "line {line}: ELA (type 04) payload is {len} bytes, must be exactly 2"
            ),
            Self::EofWithPayload { line } => write!(
                f,
                "line {line}: EOF (type 01) record carries a non-empty payload"
            ),
            Self::BadControlRecordAddress { line, kind, address } => write!(
                f,
                "line {line}: control record (type 0x{kind:02X}) has non-zero address 0x{address:04X} (must be 0x0000)"
            ),
            Self::RecordsAfterEof { line } => {
                write!(f, "line {line}: record appears after the EOF marker")
            }
            Self::MissingEof => write!(f, "missing EOF (type 01) record at end of file"),
            Self::AddressOutOfRange {
                line,
                address,
                length,
            } => write!(
                f,
                "line {line}: data record (length {length}) targets out-of-range byte address 0x{address:06X}"
            ),
            Self::DeviceIdRecord { line, address } => write!(
                f,
                "line {line}: data record targets the read-only DEVID region (0x{address:06X})"
            ),
            Self::Io { kind, path } => {
                write!(f, "I/O error reading {path}: {kind:?}")
            }
        }
    }
}

impl std::error::Error for HexLoadError {}

#[derive(Debug)]
struct ParsedRecord {
    kind: u8,
    address: u16,
    data: Vec<u8>,
}

fn parse_record(line: &str, line_no: usize) -> Result<ParsedRecord, HexLoadError> {
    let body = line.strip_prefix(':').ok_or(HexLoadError::BadStartChar { line: line_no })?;

    if body.len() < 10 {
        return Err(HexLoadError::ShortRecord {
            line: line_no,
            body_len: body.len(),
        });
    }
    if body.len() % 2 != 0 {
        return Err(HexLoadError::OddByteCount { line: line_no });
    }

    let body_bytes = body.as_bytes();
    let mut decoded = Vec::with_capacity(body.len() / 2);
    for i in (0..body.len()).step_by(2) {
        let hi = hex_digit(body_bytes[i]).ok_or(HexLoadError::BadHexDigit {
            line: line_no,
            byte_offset: i,
        })?;
        let lo = hex_digit(body_bytes[i + 1]).ok_or(HexLoadError::BadHexDigit {
            line: line_no,
            byte_offset: i + 1,
        })?;
        decoded.push((hi << 4) | lo);
    }

    let lc = decoded[0] as usize;
    if decoded.len() != lc + 5 {
        return Err(HexLoadError::ByteCountMismatch {
            line: line_no,
            declared: lc as u8,
            actual: decoded.len(),
        });
    }

    let checksum = decoded.iter().fold(0u8, |acc, &b| acc.wrapping_add(b));
    if checksum != 0 {
        // Computed = expected checksum that would have made the
        // record valid; `found` is what the record carried.
        let found = *decoded.last().expect("decoded is non-empty");
        let expected = found.wrapping_sub(checksum);
        return Err(HexLoadError::BadChecksum {
            line: line_no,
            computed: expected,
            found,
        });
    }

    let address = ((decoded[1] as u16) << 8) | decoded[2] as u16;
    let kind = decoded[3];
    let data = decoded[4..4 + lc].to_vec();

    Ok(ParsedRecord {
        kind,
        address,
        data,
    })
}

fn hex_digit(b: u8) -> Option<u8> {
    match b {
        b'0'..=b'9' => Some(b - b'0'),
        b'a'..=b'f' => Some(b - b'a' + 10),
        b'A'..=b'F' => Some(b - b'A' + 10),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fmt::Write;

    fn release_path(name: &str) -> std::path::PathBuf {
        std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .and_then(|p| p.parent())
            .expect("crate dir has 2 ancestors")
            .join("firmware/patched/releases")
            .join(name)
    }

    /// Build a syntactically correct Intel-HEX record with
    /// the right checksum.  Hand-rolling checksums in test
    /// strings is error-prone enough that *every* mistake
    /// surfaces as `BadChecksum` and masks the error path
    /// the test was actually trying to exercise.
    fn rec(kind: u8, addr: u16, data: &[u8]) -> String {
        let mut bytes = Vec::with_capacity(data.len() + 5);
        bytes.push(data.len() as u8);
        bytes.push((addr >> 8) as u8);
        bytes.push((addr & 0xFF) as u8);
        bytes.push(kind);
        bytes.extend_from_slice(data);
        let cs = bytes
            .iter()
            .fold(0u8, |acc, &b| acc.wrapping_add(b))
            .wrapping_neg();
        bytes.push(cs);

        let mut out = String::from(":");
        for b in &bytes {
            write!(&mut out, "{b:02X}").expect("write to String can't fail");
        }
        out
    }

    fn data_rec(addr: u16, data: &[u8]) -> String {
        rec(0x00, addr, data)
    }

    fn ela_rec(ela: u16) -> String {
        rec(0x04, 0x0000, &ela.to_be_bytes())
    }

    fn eof_rec() -> String {
        rec(0x01, 0x0000, &[])
    }

    // ------- helper sanity (catches helper bugs before
    // anything else) -------

    #[test]
    fn rec_helper_emits_known_good_records() {
        // Recognized golden values from a real V3.2 hex.
        assert_eq!(ela_rec(0x0000), ":020000040000FA");
        assert_eq!(ela_rec(0x0030), ":020000040030CA");
        assert_eq!(ela_rec(0x00F0), ":0200000400F00A");
        assert_eq!(eof_rec(), ":00000001FF");
    }

    // ------- parse_record happy paths -------

    #[test]
    fn parses_single_byte_data_record() {
        let r = parse_record(&data_rec(0x0000, &[0x00]), 1).unwrap();
        assert_eq!(r.kind, 0x00);
        assert_eq!(r.address, 0x0000);
        assert_eq!(r.data, vec![0x00]);
    }

    #[test]
    fn parses_eof_record() {
        let r = parse_record(&eof_rec(), 1).unwrap();
        assert_eq!(r.kind, 0x01);
        assert!(r.data.is_empty());
    }

    #[test]
    fn parses_ela_record() {
        let r = parse_record(&ela_rec(0x0030), 1).unwrap();
        assert_eq!(r.kind, 0x04);
        assert_eq!(r.data, vec![0x00, 0x30]);
    }

    // ------- parse_record error paths -------

    #[test]
    fn rejects_missing_colon() {
        let err = parse_record("0100000000FF", 7).unwrap_err();
        assert!(matches!(err, HexLoadError::BadStartChar { line: 7 }));
    }

    #[test]
    fn rejects_short_record() {
        let err = parse_record(":010000", 3).unwrap_err();
        assert!(matches!(err, HexLoadError::ShortRecord { line: 3, .. }));
    }

    #[test]
    fn rejects_odd_byte_count() {
        // 11 nibbles is odd
        let err = parse_record(":0100000000F", 4).unwrap_err();
        assert!(matches!(err, HexLoadError::OddByteCount { line: 4 }));
    }

    #[test]
    fn rejects_bad_hex_digit() {
        let err = parse_record(":0100000000ZZ", 5).unwrap_err();
        match err {
            HexLoadError::BadHexDigit { line, byte_offset } => {
                assert_eq!(line, 5);
                assert!(byte_offset >= 8);
            }
            other => panic!("expected BadHexDigit, got {other:?}"),
        }
    }

    #[test]
    fn rejects_byte_count_mismatch() {
        // LL says 02 but only 1 data byte is present.  Build by
        // hand so the checksum check still passes (otherwise that
        // error fires first).  Sum-with-zero-checksum: 02+00+00+00+00 = 0x02.
        let err = parse_record(":02000000 00 FE".replace(' ', "").as_str(), 6).unwrap_err();
        assert!(matches!(err, HexLoadError::ByteCountMismatch { line: 6, .. }));
    }

    #[test]
    fn rejects_bad_checksum() {
        // Valid 1-byte data record at addr 0 with data 0x00:
        //   :0100000000FF  (sum 0x01+0x00+0x00+0x00+0x00 = 0x01, CC=0xFF)
        // Corrupt the checksum byte to 0x00 to trigger the error.
        let err = parse_record(":010000000000", 9).unwrap_err();
        match err {
            HexLoadError::BadChecksum { line, computed, found } => {
                assert_eq!(line, 9);
                assert_eq!(computed, 0xFF);
                assert_eq!(found, 0x00);
            }
            other => panic!("expected BadChecksum, got {other:?}"),
        }
    }

    // ------- HexImage::from_hex_str happy paths -------

    fn build_hex(records: &[String]) -> String {
        let mut out = String::new();
        for r in records {
            out.push_str(r);
            out.push('\n');
        }
        out
    }

    #[test]
    fn empty_hex_with_eof_yields_default_image() {
        let img = HexImage::from_hex_str(&build_hex(&[eof_rec()])).unwrap();
        assert!(img.flash.iter().all(|&b| b == 0xFF));
        assert_eq!(img.user_id, [0xFF; USER_ID_BYTES]);
        assert_eq!(img.config, [0xFF; CONFIG_BYTES]);
        assert_eq!(img.eeprom, [0xFF; EEPROM_BYTES]);
    }

    #[test]
    fn loads_data_record_into_flash() {
        let img = HexImage::from_hex_str(&build_hex(&[
            data_rec(0x0000, &[0x00]),
            eof_rec(),
        ]))
        .unwrap();
        assert_eq!(img.flash[0], 0x00);
        assert_eq!(img.flash[1], 0xFF);
    }

    #[test]
    fn ela_routes_record_to_config_window() {
        // ELA = 0x0030 ⇒ addresses 0x300000+; 14-byte data record
        // at 0x0000 fills config[].
        let img = HexImage::from_hex_str(&build_hex(&[
            ela_rec(0x0030),
            data_rec(
                0x0000,
                &[
                    0x3A, 0x46, 0x3E, 0x1E, 0xFF, 0x00, 0x80, 0xFF, 0x0F, 0xC0, 0x0F, 0xA0, 0x0F,
                    0x40,
                ],
            ),
            eof_rec(),
        ]))
        .unwrap();
        assert_eq!(
            img.config,
            [0x3A, 0x46, 0x3E, 0x1E, 0xFF, 0x00, 0x80, 0xFF, 0x0F, 0xC0, 0x0F, 0xA0, 0x0F, 0x40]
        );
    }

    #[test]
    fn ela_routes_record_to_user_id_window() {
        let img = HexImage::from_hex_str(&build_hex(&[
            ela_rec(0x0020),
            data_rec(0x0000, &[1, 2, 3, 4, 5, 6, 7, 8]),
            eof_rec(),
        ]))
        .unwrap();
        assert_eq!(img.user_id, [1, 2, 3, 4, 5, 6, 7, 8]);
    }

    #[test]
    fn ela_routes_record_to_eeprom_window() {
        let img = HexImage::from_hex_str(&build_hex(&[
            ela_rec(0x00F0),
            data_rec(0x0000, &[0xDE, 0xAD, 0xBE, 0xEF]),
            eof_rec(),
        ]))
        .unwrap();
        assert_eq!(img.eeprom[0..4], [0xDE, 0xAD, 0xBE, 0xEF]);
    }

    // ------- HexImage::from_hex_str error paths -------

    #[test]
    fn rejects_missing_eof() {
        let err = HexImage::from_hex_str(&build_hex(&[data_rec(0x0000, &[0x00])])).unwrap_err();
        assert!(matches!(err, HexLoadError::MissingEof));
    }

    #[test]
    fn rejects_records_after_eof() {
        let err = HexImage::from_hex_str(&build_hex(&[
            eof_rec(),
            data_rec(0x0000, &[0x00]),
        ]))
        .unwrap_err();
        assert!(matches!(err, HexLoadError::RecordsAfterEof { line: 2 }));
    }

    #[test]
    fn rejects_eof_with_payload() {
        // EOF (type 01) carrying a non-empty payload.
        let bad_eof = rec(0x01, 0x0000, &[0xFF]);
        let err = HexImage::from_hex_str(&build_hex(&[bad_eof])).unwrap_err();
        assert!(matches!(err, HexLoadError::EofWithPayload { line: 1 }));
    }

    #[test]
    fn rejects_bad_ela_length() {
        // ELA (type 04) with 3 payload bytes instead of 2.
        let bad_ela = rec(0x04, 0x0000, &[0x00, 0x30, 0x40]);
        let err = HexImage::from_hex_str(&build_hex(&[bad_ela, eof_rec()])).unwrap_err();
        assert!(matches!(err, HexLoadError::BadElaLength { line: 1, len: 3 }));
    }

    #[test]
    fn rejects_unknown_record_type() {
        // Type 03 (Start Segment Address) — unsupported on PIC18.
        let weird = rec(0x03, 0x0000, &[]);
        let err = HexImage::from_hex_str(&build_hex(&[weird, eof_rec()])).unwrap_err();
        assert!(matches!(
            err,
            HexLoadError::UnknownRecordType { line: 1, kind: 0x03 }
        ));
    }

    #[test]
    fn rejects_devid_record() {
        // ELA=0x003F + addr 0xFFFE ⇒ 0x3FFFFE = DEVID base.
        let err = HexImage::from_hex_str(&build_hex(&[
            ela_rec(0x003F),
            data_rec(0xFFFE, &[0x12, 0x34]),
            eof_rec(),
        ]))
        .unwrap_err();
        match err {
            HexLoadError::DeviceIdRecord { line, address } => {
                assert_eq!(line, 2);
                assert_eq!(address, DEVID_BASE);
            }
            other => panic!("expected DeviceIdRecord, got {other:?}"),
        }
    }

    #[test]
    fn rejects_address_out_of_flash_range() {
        let err = HexImage::from_hex_str(&build_hex(&[
            data_rec(0x8000, &[0x00]),
            eof_rec(),
        ]))
        .unwrap_err();
        match err {
            HexLoadError::AddressOutOfRange { line, address, length } => {
                assert_eq!(line, 1);
                assert_eq!(address, 0x8000);
                assert_eq!(length, 1);
            }
            other => panic!("expected AddressOutOfRange, got {other:?}"),
        }
    }

    #[test]
    fn rejects_address_past_user_id_window() {
        let err = HexImage::from_hex_str(&build_hex(&[
            ela_rec(0x0020),
            data_rec(0x0008, &[0xFF]),
            eof_rec(),
        ]))
        .unwrap_err();
        match err {
            HexLoadError::AddressOutOfRange { address, .. } => {
                assert_eq!(address, USER_ID_BASE + USER_ID_BYTES as u32);
            }
            other => panic!("expected AddressOutOfRange, got {other:?}"),
        }
    }

    #[test]
    fn rejects_address_past_config_window() {
        let err = HexImage::from_hex_str(&build_hex(&[
            ela_rec(0x0030),
            data_rec(0x000E, &[0xFF]),
            eof_rec(),
        ]))
        .unwrap_err();
        match err {
            HexLoadError::AddressOutOfRange { address, .. } => {
                assert_eq!(address, CONFIG_BASE + CONFIG_BYTES as u32);
            }
            other => panic!("expected AddressOutOfRange, got {other:?}"),
        }
    }

    #[test]
    fn rejects_address_past_eeprom_window() {
        let err = HexImage::from_hex_str(&build_hex(&[
            ela_rec(0x00F0),
            data_rec(0x0100, &[0xFF]),
            eof_rec(),
        ]))
        .unwrap_err();
        match err {
            HexLoadError::AddressOutOfRange { address, .. } => {
                assert_eq!(address, EEPROM_BASE + EEPROM_BYTES as u32);
            }
            other => panic!("expected AddressOutOfRange, got {other:?}"),
        }
    }

    #[test]
    fn rejects_record_at_top_of_32_bit_space() {
        // ELA = 0xFFFF + record address 0xFFFF puts byte[0] at
        // 0xFFFF_FFFF.  That address is outside every known
        // window, so write_byte's else-branch rejects with
        // AddressOutOfRange before the loop reaches byte[1].
        // (The data-record loop's `checked_add` is defense-in-
        // depth for future window changes; with today's windows
        // it never gets a chance to fire because write_byte
        // catches the high address first.)
        let err = HexImage::from_hex_str(&build_hex(&[
            ela_rec(0xFFFF),
            data_rec(0xFFFF, &[0xAA, 0xBB]),
            eof_rec(),
        ]))
        .unwrap_err();
        match err {
            HexLoadError::AddressOutOfRange { line, address, length } => {
                assert_eq!(line, 2);
                assert_eq!(address, 0xFFFF_FFFF);
                assert_eq!(length, 2);
            }
            other => panic!("expected AddressOutOfRange, got {other:?}"),
        }
    }

    #[test]
    fn rejects_eof_with_nonzero_address() {
        // EOF (type 01) with addr != 0x0000.
        let bad_eof = rec(0x01, 0x1234, &[]);
        let err = HexImage::from_hex_str(&build_hex(&[bad_eof])).unwrap_err();
        match err {
            HexLoadError::BadControlRecordAddress { line, kind, address } => {
                assert_eq!(line, 1);
                assert_eq!(kind, 0x01);
                assert_eq!(address, 0x1234);
            }
            other => panic!("expected BadControlRecordAddress, got {other:?}"),
        }
    }

    #[test]
    fn rejects_ela_with_nonzero_address() {
        // ELA (type 04) with addr != 0x0000.
        let bad_ela = rec(0x04, 0x4242, &[0x00, 0x30]);
        let err = HexImage::from_hex_str(&build_hex(&[bad_ela, eof_rec()])).unwrap_err();
        match err {
            HexLoadError::BadControlRecordAddress { line, kind, address } => {
                assert_eq!(line, 1);
                assert_eq!(kind, 0x04);
                assert_eq!(address, 0x4242);
            }
            other => panic!("expected BadControlRecordAddress, got {other:?}"),
        }
    }

    // ------- real-fixture acceptance tests -------

    #[test]
    fn loads_v32_main_release() {
        let img = HexImage::from_hex_path(release_path("DLCP_Firmware_V3.2.hex"))
            .expect("V3.2 MAIN release hex must load cleanly");

        // All 14 CONFIG bytes match the V3.2 asm source exactly
        // (src/dlcp_fw/asm/dlcp_main_v32.asm:161-172).  Bytes 4
        // (CONFIG3L) and 7 (CONFIG4H) are unused on the 2455 and
        // come through as 0xFF.
        assert_eq!(
            img.config,
            [
                0x3A, // CONFIG1L
                0x46, // CONFIG1H (FOSC = ECPIO)
                0x3E, // CONFIG2L
                0x1E, // CONFIG2H
                0xFF, // CONFIG3L (unused on 2455)
                0x00, // CONFIG3H
                0x80, // CONFIG4L (DEBUG=1, STVREN=0)
                0xFF, // CONFIG4H (unused)
                0x0F, // CONFIG5L
                0xC0, // CONFIG5H
                0x0F, // CONFIG6L
                0xA0, // CONFIG6H
                0x0F, // CONFIG7L
                0x40, // CONFIG7H
            ]
        );

        // V3.2 places application code starting at flash 0x1000;
        // 0x000..0x1000 is the bootloader region and is not written
        // by V3.2 (so it stays at the 0xFF default).
        assert_eq!(&img.flash[0..4], &[0xFF, 0xFF, 0xFF, 0xFF]);
        // First V3.2 instruction at 0x1000 is `GOTO bootloader_start`,
        // encoded as bytes 0x0A 0xEF 0x08 0xF0.
        assert_eq!(&img.flash[0x1000..0x1004], &[0x0A, 0xEF, 0x08, 0xF0]);

        // EEPROM should have non-default content (V3.2 release ceremony
        // bumps the revision byte at eeprom[0x82] every build).
        assert!(
            img.eeprom.iter().any(|&b| b != 0xFF),
            "V3.2 EEPROM should not be all 0xFF"
        );
    }

    #[test]
    fn loads_v171_control_release() {
        let img = HexImage::from_hex_path(release_path("DLCP_Control_V1.71.hex"))
            .expect("V1.71 CONTROL release hex must load cleanly");

        // V1.71 includes the bootloader, so flash[0] is the
        // reset-vector GOTO opcode low byte (0x00) and flash[1] is
        // the GOTO prefix (0xEF).
        assert_eq!(img.flash[0], 0x00);
        assert_eq!(img.flash[1], 0xEF);

        // CONFIG is populated.
        assert!(
            img.config.iter().any(|&b| b != 0xFF),
            "V1.71 CONFIG should not be all 0xFF"
        );
    }

    // ------- Display sanity (small smoke check) -------

    #[test]
    fn errors_display_with_human_readable_messages() {
        let err = HexLoadError::BadChecksum {
            line: 4,
            computed: 0x12,
            found: 0x34,
        };
        let s = err.to_string();
        assert!(s.contains("line 4"));
        assert!(s.contains("0x34"));
        assert!(s.contains("0x12"));
    }
}
