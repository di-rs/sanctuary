mod builtins;
mod history;
mod runtime;
mod syntax;

use std::io;
use std::path::Path;
use std::process::ExitCode;

use clap::Parser;

/// Run shell commands with Brush's sh/POSIX settings.
#[derive(Parser)]
#[command(version, about)]
#[expect(clippy::struct_excessive_bools, reason = "independent CLI switches")]
#[derive(cli_schema::Schema)]
struct Args {
    /// Execute a command string; the first operand supplies $0.
    #[arg(short = 'c', conflicts_with = "stdin")]
    command: Option<String>,
    /// Force interactive shell behavior.
    #[arg(short = 'i')]
    interactive: bool,
    /// Read commands from stdin; operands supply positional parameters.
    #[arg(short = 's')]
    stdin: bool,
    /// Check syntax without executing commands.
    #[arg(short = 'n')]
    no_execute: bool,
    /// Select Brush's sh/POSIX settings (the default, not a conformance claim).
    #[arg(long = "posix", conflicts_with = "bash")]
    _posix: bool,
    /// Opt into Brush's Bash settings and extension builtins.
    #[arg(long)]
    bash: bool,
    /// Script filename and arguments, or parameters for -c/-s.
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    operands: Vec<String>,
}

impl Args {
    fn input(&self) -> Input<'_> {
        match (self.command.as_deref(), self.operands.first()) {
            (Some(command), _) => Input::Command(command),
            (None, Some(script)) if !self.stdin => Input::Script(Path::new(script)),
            _ => Input::Stdin,
        }
    }
}

enum Input<'a> {
    Command(&'a str),
    Script(&'a Path),
    Stdin,
}

impl Input<'_> {
    fn read_to_string(self) -> io::Result<String> {
        match self {
            Self::Command(command) => Ok(command.to_owned()),
            Self::Script(script) => std::fs::read_to_string(script),
            Self::Stdin => io::read_to_string(io::stdin()),
        }
    }
}

fn main() -> anyhow::Result<ExitCode> {
    <Args as cli_schema::Schema>::run(|| {
        let args = Args::parse();
        let input = args.input();
        if args.no_execute {
            return match syntax::parse(&input.read_to_string()?, args.bash) {
                Ok(_) => Ok(ExitCode::SUCCESS),
                Err(error) => {
                    eprintln!("shish: {error}");
                    Ok(ExitCode::from(2))
                }
            };
        }
        let runtime = tokio::runtime::Builder::new_multi_thread()
            .worker_threads(2)
            .enable_all()
            .build()?;
        runtime
            .block_on(runtime::run(&args, input))
            .map(ExitCode::from)
    })
}
