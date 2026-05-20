//! HD44780 character LCD slave model.
//!
//! V1.71 CONTROL drives the 16x2 character LCD via a 4-bit
//! parallel interface mapped to GPIO pins (DLCP firmware
//! `dlcp_control_v171.asm` `lcd_char_write` / `control_core_service_016E`):
//!
//!   * `LATA[5]` = RS (register select).  0 = command,
//!     1 = data.  Set BEFORE the E-pulse pair so the
//!     latched value is stable across both nibbles of one
//!     byte.
//!   * `LATB[4]` = E (enable strobe).  Pulses HIGH then LOW;
//!     the falling edge latches the current nibble into
//!     the LCD's internal shifter.
//!   * `PORTB[3:0]` = D4..D7 (4-bit data nibbles).  The
//!     firmware writes each nibble via `andwf PORTB, F` (clear
//!     low 4 bits) + `iorwf PORTB, F` (OR in nibble) so the
//!     final PORTB[3:0] at the moment of E-falling-edge is
//!     the nibble being latched.
//!
//! Per HD44780 4-bit-mode spec, the firmware sends the HIGH
//! nibble first, then the LOW nibble.  Two consecutive E
//! falling edges at the same RS form one byte; the byte is
//! then dispatched to the HD44780 instruction decoder
//! (clear-display / cursor-home / set-DDRAM / data-write).
//!
//! This model is post-event reactive: the chain's
//! `execute_core_step` calls `Hd44780::observe_pins(rs, e,
//! port_b_low_nibble)` after each controller-core instruction,
//! and the model self-tracks the previous E to detect the
//! falling edge.  Bit-exact for the firmware's write path;
//! init-sequence quirks (HD44780 needs ~5 ms warm-up + a
//! special 4-bit-mode handshake) are tolerated as long as
//! the firmware ends in 4-bit mode by the time normal
//! `lcd_char_write` calls fire.  Task #34.

use core::fmt::{self, Debug, Formatter};
use serde::{Deserialize, Serialize};

/// Length of the LCD's 16x2 character lines (bytes per
/// line).  HD44780 line widths can vary; the DLCP unit is a
/// 16-character display.
pub const LCD_LINE_LEN: usize = 16;

/// DDRAM byte addresses for line 1 / line 2 (HD44780
/// 16x2 layout).  Line 1 starts at DDRAM 0x00; line 2
/// starts at DDRAM 0x40.
const LINE1_BASE: usize = 0x00;
const LINE2_BASE: usize = 0x40;

/// Total DDRAM size we reserve.  The HD44780 has 80 bytes
/// of DDRAM (40 per line on a 40-char display).  We size
/// to 128 to leave room for the wrap-around addressing.
const DDRAM_SIZE: usize = 128;

/// Virtual HD44780 character LCD.  Owned by `Chain` as a
/// Vec entry alongside the TAS3108 slaves; coupled to a
/// controller core via `Chain::couple_lcd`.
#[derive(Serialize, Deserialize, Clone)]
pub struct Hd44780 {
    /// Display Data RAM.  16 bytes per line; line 1 starts
    /// at 0x00, line 2 at 0x40.
    #[serde(with = "serde_big_array::BigArray")]
    ddram: [u8; DDRAM_SIZE],
    /// Current write cursor (DDRAM address counter).
    cursor: u8,
    /// Previous observed E (LATB[4]) state -- used for
    /// falling-edge detection.  `false` (= E low) at POR.
    prev_e: bool,
    /// Most recent high-nibble waiting for its low-nibble
    /// pair.  `Some(high)` after the first E-falling-edge of
    /// a byte; `None` after the second (byte complete).
    pending_high_nibble: Option<u8>,
    /// Per-DDRAM-address data-write counters.  These are debug
    /// instrumentation for tests that need to prove a displayed cell is
    /// not being churned by firmware while the visible text stays the same.
    #[serde(skip, default = "default_ddram_write_counts")]
    ddram_write_counts: [u64; DDRAM_SIZE],
}

fn default_ddram_write_counts() -> [u64; DDRAM_SIZE] {
    [0; DDRAM_SIZE]
}

impl Default for Hd44780 {
    fn default() -> Self {
        Hd44780 {
            ddram: [b' '; DDRAM_SIZE],
            cursor: 0,
            prev_e: false,
            pending_high_nibble: None,
            ddram_write_counts: [0; DDRAM_SIZE],
        }
    }
}

impl Debug for Hd44780 {
    fn fmt(&self, f: &mut Formatter<'_>) -> fmt::Result {
        f.debug_struct("Hd44780")
            .field("line1", &self.line1())
            .field("line2", &self.line2())
            .field("cursor", &self.cursor)
            .field("pending_high_nibble", &self.pending_high_nibble)
            .finish()
    }
}

impl Hd44780 {
    /// Construct a fresh LCD with all DDRAM cells set to
    /// space (`b' '`) and cursor at 0x00.
    pub fn new() -> Self {
        Self::default()
    }

    /// Observe the controller's RS / E / D4-D7 pins after a
    /// single instruction step.  Implements the E-falling-
    /// edge nibble latch and pairs nibbles into bytes.
    ///
    /// `rs`: current RS (LATA[5]) value.
    /// `e`: current E (LATB[4]) value.
    /// `port_b_low_nibble`: PORTB[3:0] (already masked).
    pub fn observe_pins(&mut self, rs: bool, e: bool, port_b_low_nibble: u8) {
        let nibble = port_b_low_nibble & 0x0F;
        // Falling edge of E latches the nibble.
        if self.prev_e && !e {
            match self.pending_high_nibble.take() {
                None => {
                    // First nibble of a byte: store the
                    // high half, wait for the low nibble.
                    self.pending_high_nibble = Some(nibble);
                }
                Some(high) => {
                    // Second nibble: form the byte and
                    // dispatch to the instruction decoder.
                    let byte = (high << 4) | nibble;
                    self.apply_byte(rs, byte);
                }
            }
        }
        self.prev_e = e;
    }

    /// Apply a fully-formed 8-bit value to the HD44780
    /// state machine.  RS=0 -> command; RS=1 -> data.
    /// Public so tests can drive bytes directly without
    /// going through the pin-event path.
    pub fn apply_byte(&mut self, rs: bool, byte: u8) {
        if !rs {
            // Command.  Decode the most-significant set bit.
            // (HD44780 instruction set is one-hot in the high
            //  bits; we only model the commands the DLCP
            //  firmware actually emits.)
            match byte {
                0x01 => {
                    // Clear display.  All DDRAM = space,
                    // cursor home.
                    self.ddram = [b' '; DDRAM_SIZE];
                    self.ddram_write_counts = [0; DDRAM_SIZE];
                    self.cursor = 0;
                }
                0x02 | 0x03 => {
                    // Return home.  Cursor to 0; DDRAM
                    // preserved.  (0x02 and 0x03 differ
                    // only in the don't-care low bit.)
                    self.cursor = 0;
                }
                _ if (byte & 0x80) != 0 => {
                    // Set DDRAM address.  bit 7 set; low
                    // 7 bits = address.
                    self.cursor = byte & 0x7F;
                }
                _ => {
                    // Other commands (entry-mode,
                    // function-set, display-on/off, cursor
                    // shift) update internal LCD modes we
                    // don't model; they don't affect DDRAM
                    // contents and are silently ignored.
                }
            }
        } else {
            // Data write.  Store at cursor; advance cursor
            // (wraps in DDRAM_SIZE space).
            let idx = self.cursor as usize;
            if idx < self.ddram.len() {
                self.ddram[idx] = byte;
                self.ddram_write_counts[idx] = self.ddram_write_counts[idx].saturating_add(1);
            }
            // Cursor wraps within the 7-bit DDRAM address
            // space (per HD44780).
            self.cursor = (self.cursor + 1) & 0x7F;
        }
    }

    /// Line 1 contents (16 chars from DDRAM 0x00..0x10) as
    /// a UTF-8-lossy string.  Trailing spaces are PRESERVED
    /// so the caller can decide whether to trim.
    pub fn line1(&self) -> String {
        decode_line(&self.ddram[LINE1_BASE..LINE1_BASE + LCD_LINE_LEN])
    }

    /// Line 2 contents (16 chars from DDRAM 0x40..0x50).
    pub fn line2(&self) -> String {
        decode_line(&self.ddram[LINE2_BASE..LINE2_BASE + LCD_LINE_LEN])
    }

    /// Test-only: peek at the raw DDRAM byte at `addr`.
    /// Used by unit tests to verify cursor mechanics
    /// without going through the line-decode path.
    #[doc(hidden)]
    pub fn ddram_byte_for_test(&self, addr: u8) -> u8 {
        self.ddram[(addr as usize) & 0x7F]
    }

    /// Test-only: count data writes to a raw DDRAM byte address.
    #[doc(hidden)]
    pub fn ddram_write_count_for_test(&self, addr: u8) -> u64 {
        self.ddram_write_counts[(addr as usize) & 0x7F]
    }

    /// Test-only: peek at the cursor.
    #[doc(hidden)]
    pub fn cursor_for_test(&self) -> u8 {
        self.cursor
    }
}

/// Decode a slice of DDRAM bytes into a printable string.
/// Non-printable bytes are replaced with `?` so a partial
/// HD44780 init (where DDRAM might briefly contain raw
/// bytes from the warm-up dummy writes) doesn't blow up
/// the assertion message.
fn decode_line(bytes: &[u8]) -> String {
    bytes
        .iter()
        .map(|&b| {
            if (0x20..0x7F).contains(&b) {
                b as char
            } else {
                '?'
            }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Send one byte through the model via two pin events
    /// (high nibble then low nibble), with RS held stable.
    /// Used by the per-byte unit tests.
    fn send_byte(lcd: &mut Hd44780, rs: bool, byte: u8) {
        let high = (byte >> 4) & 0x0F;
        let low = byte & 0x0F;
        // High nibble: E up, then E down.
        lcd.observe_pins(rs, true, high);
        lcd.observe_pins(rs, false, high);
        // Low nibble: E up, then E down.
        lcd.observe_pins(rs, true, low);
        lcd.observe_pins(rs, false, low);
    }

    #[test]
    fn data_write_advances_cursor_and_lands_in_line1() {
        let mut lcd = Hd44780::new();
        // Set DDRAM=0 (line 1 start).
        send_byte(&mut lcd, false, 0x80);
        send_byte(&mut lcd, true, b'H');
        send_byte(&mut lcd, true, b'i');
        let l1 = lcd.line1();
        assert!(
            l1.starts_with("Hi"),
            "line1 should start with 'Hi', got {l1:?}"
        );
        assert_eq!(lcd.cursor_for_test(), 0x02);
    }

    #[test]
    fn set_ddram_to_line2_writes_into_line2() {
        let mut lcd = Hd44780::new();
        // 0xC0 = SET DDRAM with addr 0x40 = line 2 start.
        send_byte(&mut lcd, false, 0xC0);
        send_byte(&mut lcd, true, b'O');
        send_byte(&mut lcd, true, b'k');
        assert!(
            lcd.line2().starts_with("Ok"),
            "line2 should start with 'Ok'"
        );
    }

    #[test]
    fn clear_display_command_resets_ddram_and_cursor() {
        let mut lcd = Hd44780::new();
        send_byte(&mut lcd, false, 0x80);
        send_byte(&mut lcd, true, b'X');
        send_byte(&mut lcd, false, 0x01); // clear display
        assert_eq!(lcd.cursor_for_test(), 0x00);
        assert_eq!(lcd.line1(), " ".repeat(LCD_LINE_LEN));
    }

    #[test]
    fn nibble_pairing_handles_back_to_back_pulses() {
        // Two bytes in a row -- pin events alternate
        // high/low without any RS-only gaps in between.
        let mut lcd = Hd44780::new();
        send_byte(&mut lcd, false, 0x80); // SET DDRAM 0
        send_byte(&mut lcd, true, b'A');
        send_byte(&mut lcd, true, b'B');
        assert!(
            lcd.line1().starts_with("AB"),
            "two consecutive data bytes should land contiguously"
        );
    }

    #[test]
    fn no_e_falling_edge_means_no_state_change() {
        let mut lcd = Hd44780::new();
        // E held high the whole time -- no falling edge.
        // Even with valid PORTB nibbles + RS=1, no byte
        // should be latched.
        for _ in 0..8 {
            lcd.observe_pins(true, true, 0xA);
        }
        assert!(lcd.line1().chars().all(|c| c == ' '));
        assert_eq!(lcd.cursor_for_test(), 0x00);
    }

    #[test]
    fn rising_edge_alone_does_not_latch_nibble() {
        let mut lcd = Hd44780::new();
        // E goes 0 -> 1 (rising edge); should NOT latch.
        lcd.observe_pins(true, false, 0xA);
        lcd.observe_pins(true, true, 0xA);
        assert!(lcd.pending_high_nibble.is_none());
    }

    #[test]
    fn cursor_wraps_within_7_bit_address_space() {
        let mut lcd = Hd44780::new();
        // SET DDRAM addr to 0x7F (last cell), then write
        // one byte -- cursor should wrap to 0.
        send_byte(&mut lcd, false, 0xFF); // SET DDRAM 0x7F
        send_byte(&mut lcd, true, b'Z');
        assert_eq!(lcd.cursor_for_test(), 0x00);
    }

    #[test]
    fn line2_decode_matches_gpsim_ground_truth_shape() {
        // Reproduce the gpsim-ground-truth final state:
        // line 1 = "Volume:-17.0dB A", line 2 = "Auto Detect"
        // (padded to 16 chars in DDRAM).
        let mut lcd = Hd44780::new();
        send_byte(&mut lcd, false, 0x80); // SET DDRAM 0
        for &b in b"Volume:-17.0dB A" {
            send_byte(&mut lcd, true, b);
        }
        send_byte(&mut lcd, false, 0xC0); // SET DDRAM 0x40
        for &b in b"Auto Detect" {
            send_byte(&mut lcd, true, b);
        }
        assert_eq!(lcd.line1(), "Volume:-17.0dB A");
        // Line 2 trailing positions are still spaces.
        assert_eq!(lcd.line2(), "Auto Detect     ");
    }
}
