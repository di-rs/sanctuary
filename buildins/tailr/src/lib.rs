#![deny(clippy::print_stdout, clippy::print_stderr)]

use std::{
    collections::VecDeque,
    io::{self, BufRead, BufReader, Read, Seek, SeekFrom, Write},
    str::FromStr,
};

#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub enum TakeValue {
    PlusZero,
    TakeNum(i64),
}

enum Selection {
    Empty,
    FromStart(u64),
    FromEnd(u64),
}

impl TakeValue {
    const fn selection(self) -> Selection {
        match self {
            Self::PlusZero => Selection::FromStart(0),
            Self::TakeNum(0) => Selection::Empty,
            Self::TakeNum(n) if n > 0 => Selection::FromStart(n.unsigned_abs().saturating_sub(1)),
            Self::TakeNum(n) => Selection::FromEnd(n.unsigned_abs()),
        }
    }
}

impl FromStr for TakeValue {
    type Err = std::num::ParseIntError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        if s == "+0" {
            Ok(Self::PlusZero)
        } else {
            let mut parsed = i64::from_str(s)?;

            // if number without sign -> we should add `-`
            if !s.starts_with(['-', '+']) {
                parsed *= -1;
            }

            Ok(Self::TakeNum(parsed))
        }
    }
}

/// # Errors
/// Throws error when couldn't read the line
pub fn get_total_lines(reader: impl Read) -> Result<u64, std::io::Error> {
    let mut reader = BufReader::new(reader);
    let mut lines: u64 = 0;
    let mut buf = Vec::new();
    while let bytes_read = reader.read_until(b'\n', &mut buf)?
        && bytes_read != 0
    {
        lines = lines.saturating_add(1);
        buf.clear();
    }
    Ok(lines)
}

/// # Errors
/// Throws error when couldn't read the line or write to writer
pub fn print_lines<R: BufRead + Seek>(
    mut reader: R,
    mut writer: impl Write,
    num_lines: TakeValue,
    total_lines: u64,
) -> Result<(), std::io::Error> {
    if let Some(start) = get_start_index(num_lines, total_lines) {
        let mut buf = Vec::new();
        for _ in 0..start {
            if reader.read_until(b'\n', &mut buf)? == 0 {
                return Ok(());
            }
            buf.clear();
        }
        std::io::copy(&mut reader, &mut writer)?;
    }
    Ok(())
}

/// # Errors
/// Throws error when couldn't read the line or write to writer
pub fn print_bytes<R: Read + Seek>(
    mut reader: R,
    mut writer: impl Write,
    num_bytes: TakeValue,
    total_bytes: u64,
) -> Result<(), std::io::Error> {
    if let Some(start) = get_start_index(num_bytes, total_bytes) {
        reader.seek(SeekFrom::Start(start))?;
        std::io::copy(&mut reader, &mut writer)?;
    }
    Ok(())
}

/// Print selected bytes from a non-seekable input, retaining only the tail.
///
/// # Errors
/// Returns input read or output write errors.
pub fn print_stream_bytes(
    reader: impl BufRead,
    writer: impl Write,
    count: TakeValue,
) -> Result<(), std::io::Error> {
    print_stream(reader, writer, count, StreamUnit::Bytes)
}

/// Print selected raw lines from a non-seekable input.
///
/// # Errors
/// Returns input read or output write errors.
pub fn print_stream_lines(
    reader: impl BufRead,
    writer: impl Write,
    count: TakeValue,
) -> Result<(), std::io::Error> {
    print_stream(reader, writer, count, StreamUnit::Lines)
}

#[derive(Clone, Copy)]
enum StreamUnit {
    Bytes,
    Lines,
}

fn print_stream(
    mut reader: impl BufRead,
    mut writer: impl Write,
    count: TakeValue,
    unit: StreamUnit,
) -> io::Result<()> {
    let skip = match count.selection() {
        Selection::Empty => {
            // Zero still consumes a stream through EOF.
            io::copy(&mut reader, &mut io::sink())?;
            return Ok(());
        }
        Selection::FromStart(skip) => skip,
        Selection::FromEnd(keep) => {
            let limit = usize::try_from(keep).unwrap_or(usize::MAX);
            return match unit {
                StreamUnit::Bytes => print_last_bytes(reader, writer, limit),
                StreamUnit::Lines => print_last_lines(reader, writer, limit),
            };
        }
    };
    if skip > 0 {
        match unit {
            StreamUnit::Bytes => {
                io::copy(&mut reader.by_ref().take(skip), &mut io::sink())?;
            }
            StreamUnit::Lines => {
                for _ in 0..skip {
                    if reader.skip_until(b'\n')? == 0 {
                        return Ok(());
                    }
                }
            }
        }
    }
    io::copy(&mut reader, &mut writer)?;
    Ok(())
}

fn print_last_bytes(
    mut reader: impl BufRead,
    mut writer: impl Write,
    limit: usize,
) -> io::Result<()> {
    let mut tail = VecDeque::new();
    loop {
        let chunk = reader.fill_buf()?;
        if chunk.is_empty() {
            break;
        }
        let len = chunk.len();
        let keep = len.min(limit);
        let discard = tail.len().saturating_sub(limit.saturating_sub(keep));
        tail.drain(..discard);
        tail.extend(chunk.iter().skip(len.saturating_sub(keep)).copied());
        reader.consume(len);
    }
    let (first, second) = tail.as_slices();
    writer.write_all(first)?;
    writer.write_all(second)
}

fn print_last_lines(
    mut reader: impl BufRead,
    mut writer: impl Write,
    limit: usize,
) -> io::Result<()> {
    let mut tail = VecDeque::new();
    loop {
        let mut line = Vec::new();
        if reader.read_until(b'\n', &mut line)? == 0 {
            break;
        }
        if tail.len() == limit {
            tail.pop_front();
        }
        tail.push_back(line);
    }
    for line in tail {
        writer.write_all(&line)?;
    }
    Ok(())
}

fn get_start_index(count: TakeValue, total: u64) -> Option<u64> {
    if total == 0 {
        return None;
    }
    match count.selection() {
        Selection::Empty => None,
        Selection::FromStart(skip) => (skip < total).then_some(skip),
        Selection::FromEnd(keep) => Some(total.saturating_sub(keep)),
    }
}
