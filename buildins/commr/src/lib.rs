use std::{cmp::Ordering, io::BufRead};

#[derive(Debug, Clone, Copy)]
pub enum Column<'a> {
    Col1(&'a str),
    Col2(&'a str),
    Col3(&'a str),
}

pub trait Reporter {
    /// # Errors
    /// Returns an error when the selected column cannot be written.
    fn report(&self, col: Column) -> std::io::Result<()>;
}

/// # Errors
/// Returns decoding, input I/O, or reporter output errors
pub fn get_lines(
    reader1: impl BufRead,
    reader2: impl BufRead,
    insensitive: bool,
    reporter: &impl Reporter,
) -> std::io::Result<()> {
    let reader1 = get_lines_reader(reader1, insensitive);
    let reader2 = get_lines_reader(reader2, insensitive);

    traverse_lines(reader1, reader2, reporter)
}

fn get_lines_reader(
    reader: impl BufRead,
    insensitive: bool,
) -> impl Iterator<Item = std::io::Result<String>> {
    reader.lines().map(move |line| {
        line.map(|line| {
            if insensitive {
                line.to_lowercase()
            } else {
                line
            }
        })
    })
}

fn traverse_lines<R1, R2>(
    mut reader1: R1,
    mut reader2: R2,
    reporter: &impl Reporter,
) -> std::io::Result<()>
where
    R1: Iterator<Item = std::io::Result<String>>,
    R2: Iterator<Item = std::io::Result<String>>,
{
    let mut line1 = reader1.next().transpose()?;
    let mut line2 = reader2.next().transpose()?;

    loop {
        let column = match (line1.as_deref(), line2.as_deref()) {
            (Some(left), Some(right)) => match left.cmp(right) {
                Ordering::Less => Column::Col1(left),
                Ordering::Greater => Column::Col2(right),
                Ordering::Equal => Column::Col3(left),
            },
            (Some(left), None) => Column::Col1(left),
            (None, Some(right)) => Column::Col2(right),
            (None, None) => return Ok(()),
        };
        reporter.report(column)?;

        let advance_left = !matches!(column, Column::Col2(_));
        let advance_right = !matches!(column, Column::Col1(_));
        if advance_left {
            line1 = reader1.next().transpose()?;
        }
        if advance_right {
            line2 = reader2.next().transpose()?;
        }
    }
}
