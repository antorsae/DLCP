//! Serde helpers for fields that the standard impls + the
//! `serde-big-array` crate don't cover by themselves.
//!
//! Phase 5 (P5.1) snapshot/restore needs every Chain-reachable
//! field to be `Serialize + Deserialize`.  Most types fall out
//! of `#[derive(...)]` directly, but a few common shapes need
//! external helper modules:
//!
//! * `boxed_big_array` -- wraps `Box<[T; N]>` for any `N > 32`
//!   and any `T: Copy + Default + Serialize + Deserialize`.
//!   The `serde_big_array::BigArray` impl applies to bare
//!   `[T; N]` only; `Box<[T; N]>` requires a small wrapper that
//!   delegates the array body to BigArray, then re-boxes on
//!   deserialize.

pub mod boxed_big_array {
    use serde::de::{Deserialize, Deserializer};
    use serde::ser::{Serialize, Serializer};
    use serde_big_array::BigArray;

    pub fn serialize<S, T, const N: usize>(
        value: &Box<[T; N]>,
        serializer: S,
    ) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
        T: Serialize,
        for<'de> [T; N]: BigArray<'de, T>,
    {
        <[T; N] as BigArray<T>>::serialize(value.as_ref(), serializer)
    }

    pub fn deserialize<'de, D, T, const N: usize>(
        deserializer: D,
    ) -> Result<Box<[T; N]>, D::Error>
    where
        D: Deserializer<'de>,
        T: Deserialize<'de>,
        [T; N]: BigArray<'de, T>,
    {
        let arr: [T; N] = <[T; N] as BigArray<T>>::deserialize(deserializer)?;
        Ok(Box::new(arr))
    }
}
