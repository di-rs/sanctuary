use crate::random::rng_from_seed;
use crate::{CONTENT_LIMIT, invalid};
use anyhow::{Context, Result};
use rand::Rng;
use std::io::Write;
/// Random bytes or a repeating literal pattern (1 byte through 8 MiB).
#[derive(Clone, Debug)]
pub enum ByteSource {
    Random { seed: Option<u64> },
    Pattern(Vec<u8>),
}
/// Exact byte budget; there are no implicit record terminators.
#[derive(Clone, Debug)]
pub struct ByteOptions {
    pub bytes: u64,
    pub source: ByteSource,
}
impl ByteOptions {
    /// Validate even when the byte budget is zero.
    /// # Errors
    /// Returns `InvalidInput` for an empty or oversized literal pattern.
    pub fn validate(&self) -> Result<()> {
        if let ByteSource::Pattern(pattern) = &self.source
            && (pattern.is_empty() || pattern.len() > CONTENT_LIMIT)
        {
            return Err(invalid("byte pattern must contain 1 byte through 8 MiB"));
        }
        Ok(())
    }
}
/// Generate arbitrary bytes with an 8 KiB scratch buffer and no writer flush.
/// The budget may end anywhere in a pattern, including inside CRLF or UTF-8.
/// ```
/// let mut output=Vec::new();
/// let options=biggie::ByteOptions{bytes:3,source:biggie::ByteSource::Pattern(vec![0,255])};
/// biggie::generate_bytes(&mut output,&options)?;
/// assert_eq!(output,[0,255,0]);
/// # Ok::<(), anyhow::Error>(())
/// ```
/// # Errors
/// Invalid options fail before writing; write errors preserve partial output.
pub fn generate_bytes(writer: impl Write, options: &ByteOptions) -> Result<()> {
    options.validate()?;
    match &options.source {
        ByteSource::Random { seed } => {
            let mut rng = rng_from_seed(*seed);
            write_chunks(writer, options.bytes, |chunk| rng.fill_bytes(chunk))
        }
        ByteSource::Pattern(pattern) => {
            let mut pattern = pattern.iter().copied().cycle();
            write_chunks(writer, options.bytes, |chunk| {
                for (byte, value) in chunk.iter_mut().zip(&mut pattern) {
                    *byte = value;
                }
            })
        }
    }
}

fn write_chunks(
    mut writer: impl Write,
    byte_count: u64,
    mut fill_chunk: impl FnMut(&mut [u8]),
) -> Result<()> {
    log::debug!(requested_bytes = byte_count; "generating bytes");
    let mut buffer = [0_u8; 8192];
    let mut remaining = byte_count;
    while remaining > 0 {
        let count = remaining.min(8192);
        let bytes = buffer
            .get_mut(..usize::try_from(count)?)
            .context("invalid byte buffer length")?;
        fill_chunk(bytes);
        writer
            .write_all(bytes)
            .context("Cannot write generated data")?;
        remaining = remaining.saturating_sub(count);
    }
    log::debug!(bytes_written = byte_count; "generation complete");
    Ok(())
}
