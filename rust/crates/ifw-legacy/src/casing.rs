//! Applying an explicitly supplied .NET invariant-casing reference map.
//!
//! There is no bundled or implicitly trusted map. RW-02 generates the complete
//! mapping with C# on each native target and compares it before any shipping
//! table is adopted. Rust's expanding Unicode uppercase is not a compatible fallback.

/// A structurally checked simple-scalar map, whose semantic provenance the caller
/// must independently establish. Unlisted scalars are identity mappings.
///
/// This type validates shape and idempotence, not completeness or compatibility
/// with a particular .NET/ICU version. Never accept user-supplied maps as a product
/// configuration option. The development probe supplies only its synthetic oracle.
#[derive(Debug, Clone)]
pub struct ReferenceCaseMap {
    pairs: Vec<(char, char)>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct InvalidCaseMap;

impl std::fmt::Display for InvalidCaseMap {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("invalid invariant-casing reference map")
    }
}

impl std::error::Error for InvalidCaseMap {}

impl ReferenceCaseMap {
    /// Accept sorted, unique, changed scalar pairs with unchanged UTF-16 lengths.
    /// A full-map source/provenance check remains the caller's responsibility.
    pub fn from_reference_pairs(pairs: Vec<(char, char)>) -> Result<Self, InvalidCaseMap> {
        if pairs.len() > 10_000
            || pairs
                .iter()
                .any(|(from, to)| from == to || from.len_utf16() != to.len_utf16())
            || pairs.windows(2).any(|pair| pair[0].0 >= pair[1].0)
        {
            return Err(InvalidCaseMap);
        }
        let map = Self { pairs };
        if map
            .pairs
            .iter()
            .any(|(_, to)| map.uppercase_char(*to) != *to)
        {
            return Err(InvalidCaseMap);
        }
        Ok(map)
    }

    pub fn changed_scalar_count(&self) -> usize {
        self.pairs.len()
    }

    /// Apply simple mappings only, preserving characters such as sharp-S that
    /// full Unicode uppercase could expand into a different path identity.
    pub fn uppercase(&self, input: &str) -> String {
        input
            .chars()
            .map(|value| self.uppercase_char(value))
            .collect()
    }

    /// Preserve unpaired UTF-16 surrogates while mapping valid scalar pairs.
    /// Windows path identities need not be losslessly representable as Rust `String`.
    pub fn uppercase_utf16(&self, input: &[u16]) -> Vec<u16> {
        let mut output = Vec::with_capacity(input.len());
        for value in char::decode_utf16(input.iter().copied()) {
            match value {
                Ok(value) => {
                    let mut buffer = [0; 2];
                    output.extend_from_slice(self.uppercase_char(value).encode_utf16(&mut buffer));
                }
                Err(error) => output.push(error.unpaired_surrogate()),
            }
        }
        output
    }

    fn uppercase_char(&self, input: char) -> char {
        self.pairs
            .binary_search_by_key(&input, |pair| pair.0)
            .map_or(input, |index| self.pairs[index].1)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn supplied_reference_preserves_nonexpanding_and_unpaired_utf16() {
        let map = ReferenceCaseMap::from_reference_pairs(vec![('a', 'A'), ('i', 'I'), ('𐐨', '𐐀')])
            .unwrap();
        assert_eq!(map.uppercase("aßıİiﬃ𐐨"), "AßıİIﬃ𐐀");
        assert_ne!(map.uppercase("ß"), "ß".to_uppercase());
        assert_eq!(
            map.uppercase_utf16(&[0xd800, 0x61, 0xdc00]),
            vec![0xd800, 0x41, 0xdc00]
        );
    }

    #[test]
    fn ambiguous_nonidempotent_and_expanding_maps_are_rejected() {
        for pairs in [
            vec![('a', 'A'), ('a', 'B')],
            vec![('z', 'Z'), ('a', 'A')],
            vec![('a', 'b'), ('b', 'C')],
            vec![('a', 'a')],
            vec![('a', '𐐀')],
        ] {
            assert!(ReferenceCaseMap::from_reference_pairs(pairs).is_err());
        }
    }
}
