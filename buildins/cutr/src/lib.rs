use csv::StringRecord;
use std::{
    io::{self, BufRead, Write},
    range::Range,
};

mod positionlist;
use crate::positionlist::PositionList;
pub use positionlist::ParseError;

#[derive(Debug)]
pub enum Extract {
    Fields(PositionList),
    Bytes(PositionList),
    Chars(PositionList),
}

impl Extract {
    /// # Errors
    /// Throws error if unable to decode line in the reader or write to writer is failed
    pub fn extract(
        &self,
        reader: impl BufRead,
        writer: impl Write,
        delimiter: u8,
    ) -> io::Result<()> {
        match self {
            Self::Bytes(positions) => write_lines(reader, writer, positions.inner(), extract_bytes),
            Self::Chars(positions) => write_lines(reader, writer, positions.inner(), extract_chars),
            Self::Fields(positions) => {
                let mut rdr = csv::ReaderBuilder::new()
                    .delimiter(delimiter)
                    .has_headers(false)
                    .from_reader(reader);
                let mut wrt = csv::WriterBuilder::new()
                    .delimiter(delimiter)
                    .from_writer(writer);

                for record in rdr.records() {
                    wrt.write_record(extract_fields(&record?, positions.inner()))?;
                }
                Ok(())
            }
        }
    }
}

fn write_lines(
    reader: impl BufRead,
    mut writer: impl Write,
    positions: &[Range<usize>],
    extract: impl Fn(&str, &[Range<usize>]) -> String,
) -> io::Result<()> {
    for line in reader.lines() {
        let extracted = extract(&line?, positions);
        writeln!(writer, "{extracted}")?;
    }
    Ok(())
}

fn select<T>(
    positions: &[Range<usize>],
    len: usize,
    get: impl FnMut(usize) -> Option<T>,
) -> impl Iterator<Item = T> {
    positions
        .iter()
        .flat_map(move |range| range.start..range.end.min(len))
        .filter_map(get)
}

fn extract_chars(line: &str, char_pos: &[Range<usize>]) -> String {
    let chars: Vec<_> = line.chars().collect();
    select(char_pos, chars.len(), |index| chars.get(index)).collect()
}

fn extract_bytes(line: &str, byte_pos: &[Range<usize>]) -> String {
    let bytes = line.as_bytes();
    let selected: Vec<_> =
        select(byte_pos, bytes.len(), |index| bytes.get(index).copied()).collect();
    String::from_utf8_lossy(&selected).into_owned()
}

fn extract_fields<'record>(
    record: &'record StringRecord,
    field_pos: &[Range<usize>],
) -> impl Iterator<Item = &'record str> {
    select(field_pos, record.len(), move |index| record.get(index))
}

#[cfg(test)]
mod tests {
    use super::*;
    use pretty_assertions::assert_eq;

    #[test]
    fn extract_chars_empty_string() {
        let res = extract_chars("", &[Range::from(0..1)]);
        let expected = "";
        assert_eq!(res, expected);
    }

    #[test]
    fn extract_chars_single_range() {
        let res = extract_chars("ébc", &[Range::from(0..1)]);
        let expected = "é";
        assert_eq!(res, expected);
    }

    #[test]
    fn extract_chars_two_ranges() {
        let res = extract_chars("ébc", &[Range::from(0..1), Range::from(2..3)]);
        let expected = "éc";
        assert_eq!(res, expected);
    }

    #[test]
    fn extract_chars_full_range() {
        let res = extract_chars("ébc", &[Range::from(0..3)]);
        let expected = "ébc";
        assert_eq!(res, expected);
    }

    #[test]
    fn extract_chars_two_unordered_ranges() {
        let res = extract_chars("ébc", &[Range::from(2..3), Range::from(1..2)]);
        let expected = "cb";
        assert_eq!(res, expected);
    }

    #[test]
    fn extract_chars_with_missing_range() {
        let res = extract_chars(
            "ébc",
            &[Range::from(0..1), Range::from(1..2), Range::from(4..5)],
        );
        let expected = "éb";
        assert_eq!(res, expected);
    }

    #[test]
    fn extract_bytes_empty_string() {
        let res = extract_bytes("", &[Range::from(0..1)]);
        let expected = "";
        assert_eq!(res, expected);
    }

    #[test]
    fn extract_bytes_single_range_unicode_split() {
        let res = extract_bytes("ébc", &[Range::from(0..1)]);
        let expected = "�";
        assert_eq!(res, expected);
    }

    #[test]
    fn extract_bytes_single_range() {
        let res = extract_bytes("ébc", &[Range::from(0..2)]);
        let expected = "é";
        assert_eq!(res, expected);
    }

    #[test]
    fn extract_bytes_two_chars() {
        let res = extract_bytes("ébc", &[Range::from(0..3)]);
        let expected = "éb";
        assert_eq!(res, expected);
    }

    #[test]
    fn extract_bytes_full_range() {
        let res = extract_bytes("ébc", &[Range::from(0..4)]);
        let expected = "ébc";
        assert_eq!(res, expected);
    }

    #[test]
    fn extract_bytes_two_ranges() {
        let res = extract_bytes("ébc", &[Range::from(3..4), Range::from(2..3)]);
        let expected = "cb";
        assert_eq!(res, expected);
    }

    #[test]
    fn extract_bytes_with_missing_range() {
        let res = extract_bytes("ébc", &[Range::from(0..2), Range::from(5..6)]);
        let expected = "é";
        assert_eq!(res, expected);
    }

    #[test]
    fn extract_fields_single_range() {
        let input = StringRecord::from(vec!["Captain", "Sham", "12345"]);
        let res: Vec<_> = extract_fields(&input, &[Range::from(0..1)]).collect();
        let expected = &["Captain"];
        assert_eq!(res, expected);
    }

    #[test]
    fn extract_fields_single_range_second() {
        let input = StringRecord::from(vec!["Captain", "Sham", "12345"]);
        let res: Vec<_> = extract_fields(&input, &[Range::from(1..2)]).collect();
        let expected = &["Sham"];
        assert_eq!(res, expected);
    }

    #[test]
    fn extract_fields_two_ranges() {
        let input = StringRecord::from(vec!["Captain", "Sham", "12345"]);
        let res: Vec<_> = extract_fields(&input, &[Range::from(0..1), Range::from(2..3)]).collect();
        let expected = &["Captain", "12345"];
        assert_eq!(res, expected);
    }

    #[test]
    fn extract_fields_with_missing_range() {
        let input = StringRecord::from(vec!["Captain", "Sham", "12345"]);
        let res: Vec<_> = extract_fields(&input, &[Range::from(0..1), Range::from(3..4)]).collect();
        let expected = &["Captain"];
        assert_eq!(res, expected);
    }

    #[test]
    fn extract_fields_unordered_ranges() {
        let input = StringRecord::from(vec!["Captain", "Sham", "12345"]);
        let res: Vec<_> = extract_fields(&input, &[Range::from(1..2), Range::from(0..1)]).collect();
        let expected = &["Sham", "Captain"];
        assert_eq!(res, expected);
    }
}
