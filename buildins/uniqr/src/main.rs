use clap::CommandFactory;
use std::{
    fs::File,
    io::{self, BufReader, BufWriter, IsTerminal, Stdin, Write, stdin},
    os::{fd::AsFd, unix::fs::MetadataExt},
};

mod cli;
use crate::cli::{Cli, CliError};
use uniqr::{UniqueList, report_unique_lines};

enum Input {
    Stdin(Stdin),
    File(File),
}

fn main() -> std::process::ExitCode {
    cli_log::run("uniqr", |cli| match run(cli) {
        Ok(()) => exitcode::OK,
        Err(CliError::Config) => {
            cli_log::record_error(CliError::Config);
            exitcode::CONFIG
        }
        Err(CliError::FileOpen { err, path }) => {
            cli_log::record_error(format_args!("{path}: {err}"));
            eprint!("{path}: {err}");
            exitcode::IOERR
        }
        Err(e) => {
            cli_log::diagnostic!("Error: {e}");
            exitcode::DATAERR
        }
    })
}

fn run(cli: Cli) -> Result<(), CliError> {
    let input = open_input(&cli.input_file)?;
    let mut writer = get_writer(cli.output_file, &input)?;

    let list = match input {
        Input::Stdin(stdin) => UniqueList::from_reader(stdin.lock()),
        Input::File(file) => UniqueList::from_reader(BufReader::new(file)),
    }?;
    report_unique_lines(&mut writer, list, cli.count)?;
    writer.flush()?;

    Ok(())
}

fn open_input(path: &str) -> Result<Input, CliError> {
    if path == "-" {
        let stdin = stdin();
        if stdin.is_terminal() {
            let _ = Cli::command().print_help();
            return Err(CliError::Config);
        }
        Ok(Input::Stdin(stdin))
    } else {
        let file = File::open(path).map_err(|err| CliError::FileOpen {
            err,
            path: path.to_string(),
        })?;
        Ok(Input::File(file))
    }
}

fn get_writer(path: Option<String>, input: &Input) -> Result<Box<dyn Write>, CliError> {
    if let Some(path) = path {
        let file = std::fs::OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(false)
            .open(&path)
            .map_err(|err| CliError::FileOpen {
                err,
                path: path.clone(),
            })?;
        let target = file.metadata()?;
        let source = match input {
            Input::File(file) => Some(file.metadata()?),
            Input::Stdin(stdin) if target.is_file() => {
                Some(File::from(stdin.as_fd().try_clone_to_owned()?).metadata()?)
            }
            Input::Stdin(_) => None,
        };
        if let Some(source) = source
            && source.dev() == target.dev()
            && source.ino() == target.ino()
        {
            return Err(io::Error::other("input and output refer to the same file").into());
        }
        if target.is_file() {
            file.set_len(0)?;
        }
        Ok(Box::new(BufWriter::new(file)))
    } else {
        let stdout = std::io::stdout();
        Ok(Box::new(BufWriter::new(stdout.lock())))
    }
}
