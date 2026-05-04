//! Phase 5 (P5.1) snapshot/restore for [`crate::chain::Chain`].
//!
//! `encode(&Chain)` returns a `Vec<u8>` bincode blob; `decode(&[u8])`
//! restores a `Chain` from that blob and verifies no trailing bytes
//! remain.  The round-trip is byte-stable: `encode(decode(b)?)? == b`.
//!
//! Spec reference: `docs/SIM_REWRITE_RUST_SPEC.md` §9.

use crate::chain::Chain;

/// Snapshot/restore failure modes.
#[derive(Debug)]
pub enum DecodeError {
    /// Underlying bincode decode error (truncated data, version
    /// mismatch, schema drift).
    Bincode(bincode::error::DecodeError),
    /// The input had bytes left over after the chain was fully
    /// reconstructed.  Indicates either corrupt input or a caller
    /// using `decode` with a longer buffer than expected.
    TrailingBytes { consumed: usize, total: usize },
}

impl From<bincode::error::DecodeError> for DecodeError {
    fn from(e: bincode::error::DecodeError) -> Self {
        Self::Bincode(e)
    }
}

impl core::fmt::Display for DecodeError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            DecodeError::Bincode(e) => write!(f, "bincode decode error: {e}"),
            DecodeError::TrailingBytes { consumed, total } => {
                write!(
                    f,
                    "trailing bytes after Chain decode: consumed {consumed} of {total}"
                )
            }
        }
    }
}

impl std::error::Error for DecodeError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            DecodeError::Bincode(e) => Some(e),
            DecodeError::TrailingBytes { .. } => None,
        }
    }
}

/// Encode a chain to a bincode blob.
pub fn encode(chain: &Chain) -> Vec<u8> {
    bincode::serde::encode_to_vec(chain, bincode::config::standard())
        .expect("Chain bincode encode to Vec<u8> cannot fail")
}

/// Decode a chain from a bincode blob.
pub fn decode(bytes: &[u8]) -> Result<Chain, DecodeError> {
    let (chain, consumed): (Chain, usize) =
        bincode::serde::decode_from_slice(bytes, bincode::config::standard())?;
    if consumed != bytes.len() {
        return Err(DecodeError::TrailingBytes {
            consumed,
            total: bytes.len(),
        });
    }
    Ok(chain)
}

impl Chain {
    /// Encode this chain to a bincode blob.
    pub fn snapshot(&self) -> Vec<u8> {
        encode(self)
    }

    /// Decode a chain from a bincode blob.
    pub fn restore(bytes: &[u8]) -> Result<Self, DecodeError> {
        decode(bytes)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Empty chain (no cores) round-trips byte-stably.
    #[test]
    fn empty_chain_round_trip_is_byte_stable() {
        let chain = Chain::new();
        let bytes = encode(&chain);
        let restored = decode(&bytes).expect("snapshot decodes");
        let bytes2 = encode(&restored);
        assert_eq!(bytes, bytes2, "round-trip must be byte-stable");
    }

    /// After advancing the universal clock, the snapshot still
    /// round-trips and the restored chain has the same current_tick.
    #[test]
    fn empty_chain_after_step_round_trips() {
        let mut chain = Chain::new();
        chain.step_ticks(12_345);
        let bytes = encode(&chain);
        let restored = decode(&bytes).expect("snapshot decodes");
        assert_eq!(restored.current_tick, 12_345);
        assert_eq!(encode(&restored), bytes);
    }

    /// Trailing-bytes detection: appending garbage to a valid blob
    /// must surface as `DecodeError::TrailingBytes`.
    #[test]
    fn trailing_bytes_are_rejected() {
        let chain = Chain::new();
        let mut bytes = encode(&chain);
        bytes.push(0xFF);
        match decode(&bytes) {
            Err(DecodeError::TrailingBytes { consumed, total }) => {
                assert_eq!(total, consumed + 1);
            }
            Err(e) => panic!("expected TrailingBytes, got Err({e:?})"),
            Ok(_) => panic!("expected TrailingBytes, got Ok(_)"),
        }
    }
}
