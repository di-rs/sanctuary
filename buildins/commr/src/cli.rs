use clap::{ArgAction, Parser};
use std::path::PathBuf;
use thiserror::Error;

use commr::{Column, Reporter};

#[allow(
    clippy::struct_excessive_bools,
    reason = "Clap models independent command-line switches as booleans."
)]
#[derive(Parser, Debug)]
#[command(author, version, about)]
/// Rust minimal `comm` implementation
/// Input file lines should be sorted
#[derive(cli_schema::Schema)]
pub struct Cli {
    /// First file to compare, use `-` to read from stdin
    #[arg(value_name = "FILE_1", required(true))]
    pub file1: PathBuf,

    /// Second file to compare, use `-` to read from stdin
    #[arg(value_name = "FILE_2", required(true))]
    pub file2: PathBuf,

    /// Suppress printing of column 1
    #[arg(short('1'), default_value = "true", action(ArgAction::SetFalse))]
    show_col1: bool,

    /// Suppress printing of column 2
    #[arg(short('2'), default_value = "true", action(ArgAction::SetFalse))]
    show_col2: bool,

    /// Suppress printing of column 3
    #[arg(short('3'), default_value = "true", action(ArgAction::SetFalse))]
    show_col3: bool,

    /// Case-insensitive comparison of lines
    #[arg(short('i'), long)]
    pub insensitive: bool,

    /// Output delimiter
    #[arg(
        value_name = "DELIM",
        short('d'),
        long("output-delimiter"),
        default_value = "\t"
    )]
    delimiter: String,
}

#[derive(Error, Debug)]
pub enum CliError {
    #[error("incorrect config passed")]
    Config,
    #[error("both input files cannot be STDIN (`-`)")]
    BothFilesStdin,
    #[error("cannot open provided file")]
    FileOpen(PathBuf, std::io::Error),
    #[error(transparent)]
    IO(#[from] std::io::Error),
}

impl Reporter for Cli {
    fn report(&self, col: Column) -> std::io::Result<()> {
        use std::io::Write;

        let (value, preceding) = match col {
            Column::Col1(value) if self.show_col1 => (value, [false, false]),
            Column::Col2(value) if self.show_col2 => (value, [self.show_col1, false]),
            Column::Col3(value) if self.show_col3 => (value, [self.show_col1, self.show_col2]),
            _ => return Ok(()),
        };
        let separators = preceding.into_iter().filter(|&visible| visible).count();
        let prefix = self.delimiter.repeat(separators);
        writeln!(std::io::stdout().lock(), "{prefix}{value}")
    }
}
