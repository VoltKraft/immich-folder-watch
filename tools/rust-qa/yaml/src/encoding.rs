//! Decode a bounded synthetic file as the legacy File.ReadAllText reader does.

use crate::codec::Failure;
use std::io::Read;

#[derive(Clone, Copy)]
pub enum Encoding {
    Utf8 = 65001,
    Utf16Le = 1200,
    Utf16Be = 1201,
    Utf32Le = 12000,
    Utf32Be = 12001,
}

fn detect(bytes: &[u8]) -> (Encoding, &[u8]) {
    use Encoding::*;
    match bytes {
        [0xff, 0xfe, 0, 0, text @ ..] => (Utf32Le, text),
        [0, 0, 0xfe, 0xff, text @ ..] => (Utf32Be, text),
        [0xff, 0xfe, text @ ..] => (Utf16Le, text),
        [0xfe, 0xff, text @ ..] => (Utf16Be, text),
        [0xef, 0xbb, 0xbf, text @ ..] => (Utf8, text),
        _ => (Utf8, bytes),
    }
}

pub struct Decoded {
    pub text: String,
    pub encoding: Encoding,
    pub had_errors: bool,
    pub source_bytes: usize,
}

impl Decoded {
    fn push_text(&mut self, text: &str, limit: usize) -> Result<(), Failure> {
        if text.len() > limit - self.text.len() {
            return Err(Failure::InputBytes);
        }
        self.text.push_str(text);
        Ok(())
    }

    fn push_scalar(&mut self, scalar: Option<char>, limit: usize) -> Result<(), Failure> {
        self.had_errors |= scalar.is_none();
        self.push_text(
            scalar
                .unwrap_or(char::REPLACEMENT_CHARACTER)
                .encode_utf8(&mut [0; 4]),
            limit,
        )
    }
}

pub fn read(reader: impl Read, file_limit: usize, text_limit: usize) -> Result<Decoded, Failure> {
    let mut bytes = Vec::new();
    reader
        .take((file_limit as u64).saturating_add(1))
        .read_to_end(&mut bytes)
        .map_err(|error| Failure::InputIo(error.kind()))?;
    if bytes.len() > file_limit {
        return Err(Failure::InputBytes);
    }
    let (encoding, content) = detect(&bytes);
    let mut decoded = Decoded {
        text: String::with_capacity(content.len().min(text_limit)),
        encoding,
        had_errors: false,
        source_bytes: bytes.len(),
    };
    match encoding {
        Encoding::Utf8 => {
            for chunk in content.utf8_chunks() {
                decoded.push_text(chunk.valid(), text_limit)?;
                if !chunk.invalid().is_empty() {
                    decoded.push_scalar(None, text_limit)?;
                }
            }
        }
        Encoding::Utf16Le | Encoding::Utf16Be => {
            let (words, trailing) = content.as_chunks::<2>();
            let word = match encoding {
                Encoding::Utf16Le => u16::from_le_bytes,
                _ => u16::from_be_bytes,
            };
            for scalar in char::decode_utf16(words.iter().copied().map(word)) {
                decoded.push_scalar(scalar.ok(), text_limit)?;
            }
            if !trailing.is_empty() {
                decoded.push_scalar(None, text_limit)?;
            }
        }
        Encoding::Utf32Le | Encoding::Utf32Be => {
            let (words, trailing) = content.as_chunks::<4>();
            let word = match encoding {
                Encoding::Utf32Le => u32::from_le_bytes,
                _ => u32::from_be_bytes,
            };
            for &value in words {
                decoded.push_scalar(char::from_u32(word(value)), text_limit)?;
            }
            if !trailing.is_empty() {
                decoded.push_scalar(None, text_limit)?;
            }
        }
    }
    Ok(decoded)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{self, Cursor};

    struct SingleBytes<'a>(&'a [u8]);

    impl Read for SingleBytes<'_> {
        fn read(&mut self, buffer: &mut [u8]) -> io::Result<usize> {
            let length = buffer.len().min(1);
            self.0.read(&mut buffer[..length])
        }
    }

    #[test]
    fn detects_boms_and_preserves_scalars_across_short_reads() {
        let text = "文😀�\u{feff}";
        let mut cases = vec![
            (65001, Vec::new(), text.as_bytes().to_vec()),
            (65001, vec![0xef, 0xbb, 0xbf], text.as_bytes().to_vec()),
        ];
        cases.push((
            1200,
            vec![0xff, 0xfe],
            text.encode_utf16().flat_map(u16::to_le_bytes).collect(),
        ));
        cases.push((
            1201,
            vec![0xfe, 0xff],
            text.encode_utf16().flat_map(u16::to_be_bytes).collect(),
        ));
        cases.push((
            12000,
            vec![0xff, 0xfe, 0, 0],
            text.chars()
                .map(u32::from)
                .flat_map(u32::to_le_bytes)
                .collect(),
        ));
        cases.push((
            12001,
            vec![0, 0, 0xfe, 0xff],
            text.chars()
                .map(u32::from)
                .flat_map(u32::to_be_bytes)
                .collect(),
        ));
        for (code_page, mut bytes, payload) in cases {
            bytes.extend(payload);
            let decoded = read(SingleBytes(&bytes), 64, 64).unwrap();
            assert_eq!(decoded.encoding as u16, code_page);
            assert_eq!(decoded.source_bytes, bytes.len());
            assert_eq!(decoded.text, text);
            assert!(!decoded.had_errors);
        }
    }

    #[test]
    fn distinguishes_replacement_fallback_from_a_literal_replacement_character() {
        for (bytes, code_page, text) in [
            (&[0xef, 0xbb][..], 65001, "�"),
            (&[0xed, 0xa0, 0x80], 65001, "���"),
            (&[0xf0, 0x9f, 0x98], 65001, "�"),
            (&[0xff, 0xfe, 0], 1200, "�"),
            (&[0xff, 0xfe, 0, 0xd8, 0], 1200, "��"),
            (&[0xfe, 0xff, 0xdc, 1, 0, 0x61], 1201, "�a"),
            (&[0xff, 0xfe, 0, 0, 0, 0xd8, 0, 0, 7], 12000, "��"),
            (&[0, 0, 0xfe, 0xff, 0, 0x11, 0, 0, 1, 2, 3], 12001, "��"),
        ] {
            let decoded = read(SingleBytes(bytes), 64, 64).unwrap();
            assert_eq!(decoded.encoding as u16, code_page);
            assert_eq!(decoded.text, text);
            assert!(decoded.had_errors);
        }
    }

    #[test]
    fn bounds_original_reads_and_utf8_expansion_independently() {
        let mut source = Cursor::new(b"0123456789");
        assert!(matches!(read(&mut source, 3, 64), Err(Failure::InputBytes)));
        assert_eq!(source.position(), 4);
        assert_eq!(read(&b"abc"[..], 3, 3).unwrap().text, "abc");
        assert_eq!(read(&[][..], 0, 0).unwrap().text, "");
        assert_eq!(read(&[0xff, 0xff][..], 2, 6).unwrap().text, "��");
        assert!(matches!(
            read(&[0xff, 0xff][..], 2, 5),
            Err(Failure::InputBytes)
        ));
        let wide = [0xff, 0xfe, 0x00, 0x4e, 0x01, 0x4e, 0x02, 0x4e];
        assert!(matches!(read(&wide[..], 8, 8), Err(Failure::InputBytes)));
        assert_eq!(read(&wide[..], 8, 9).unwrap().text.len(), 9);
    }
}
