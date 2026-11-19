//! CLI-to-Brush integration. Brush owns evaluation and shell state.

use std::collections::HashMap;
use std::fs::File;
use std::io::{self, BufRead as _, IsTerminal as _};
use std::os::fd::AsFd as _;
use std::sync::Arc;

use brush_core::{ExecutionControlFlow, Shell, ShellVariable, SourceInfo};
use brush_interactive::{InteractiveOptions, InteractiveShell, ReedlineInputBackend, UIOptions};

use crate::{Args, Input};

pub async fn run(args: &Args, input: Input<'_>) -> anyhow::Result<u8> {
    let from_stdin = matches!(input, Input::Stdin);
    let interactive =
        args.interactive || (from_stdin && io::stdin().is_terminal() && io::stderr().is_terminal());
    let interactive_terminal = interactive && io::stdin().is_terminal();
    let (shell_name, shell_args) = match args.operands.as_slice() {
        [name, operands @ ..] if !from_stdin => (name.as_str(), operands),
        operands => ("shish", operands),
    };
    // Use an unbuffered descriptor for builtins too: Rust's shared stdin buffer
    // must not consume bytes intended for the next shell command.
    let stdin = File::from(io::stdin().as_fd().try_clone_to_owned()?);
    let mut shell = Shell::builder()
        .builtins(crate::history::builtins(if args.bash {
            brush_builtins::BuiltinSet::BashMode
        } else {
            brush_builtins::BuiltinSet::ShMode
        }))
        .builtin(
            "true",
            brush_core::builtins::simple_builtin::<crate::builtins::Status<true>, _>(),
        )
        .builtin(
            "false",
            brush_core::builtins::simple_builtin::<crate::builtins::Status<false>, _>(),
        )
        .shell_name(shell_name.to_owned())
        .shell_args(shell_args.to_vec())
        .shell_product_display_str(format!("shish {}", env!("CARGO_PKG_VERSION")))
        .interactive(interactive)
        .read_commands_from_stdin(from_stdin)
        .command_string_mode(matches!(input, Input::Command(_)))
        .sh_mode(!args.bash)
        .posix(!args.bash)
        .profile(brush_core::ProfileLoadBehavior::Skip)
        .rc(brush_core::RcLoadBehavior::Skip)
        .fds(HashMap::from([(0, stdin.into())]))
        .var(
            "PS1",
            ShellVariable::new(std::env::var("PS1").unwrap_or_else(|_| String::from(r"\W > "))),
        )
        .build()
        .await?;

    // The REPL acquires the terminal itself. With -i and a command or script,
    // foreground children need the same job-control setup before they exec.
    let _terminal = (interactive_terminal && !from_stdin)
        .then(brush_core::terminal::TerminalControl::acquire)
        .transpose()?;
    match input {
        Input::Command(command) => Ok(shell
            .run_dash_c_command(command.to_owned())
            .await?
            .exit_code
            .into()),
        Input::Script(script) => Ok(shell
            .run_script(script, shell_args.iter().cloned())
            .await?
            .exit_code
            .into()),
        Input::Stdin if interactive_terminal => {
            let shell = Arc::new(tokio::sync::Mutex::new(shell));
            let options = UIOptions::default();
            let mut backend = ReedlineInputBackend::new(&options, &shell)?;
            InteractiveShell::new(&shell, &mut backend, &InteractiveOptions::from(&options))?
                .run_interactively()
                .await?;
            Ok(shell.lock().await.last_exit_status())
        }
        Input::Stdin => run_stdin(&mut shell).await,
    }
}

async fn run_stdin(shell: &mut Shell) -> anyhow::Result<u8> {
    let stdin = File::from(io::stdin().as_fd().try_clone_to_owned()?);
    // Capacity one prevents read-ahead from consuming command input (e.g. read).
    let mut reader = io::BufReader::with_capacity(1, stdin);
    let mut input = String::new();
    loop {
        let at_eof = reader.read_line(&mut input)? == 0;
        if at_eof && input.is_empty() {
            break;
        }
        let incomplete = match shell.parse_string(input.clone()) {
            Err(brush_parser::ParseError::ParsingAtEndOfInput) => true,
            Err(brush_parser::ParseError::Tokenizing { inner, .. }) => inner.is_incomplete(),
            _ => false,
        };
        if incomplete && !at_eof {
            continue;
        }
        let params = shell.default_exec_params();
        let result = shell
            .run_string(
                std::mem::take(&mut input),
                &SourceInfo::from("stdin"),
                &params,
            )
            .await?;
        if matches!(result.next_control_flow, ExecutionControlFlow::ExitShell) || at_eof {
            break;
        }
    }
    shell.on_exit().await?;
    Ok(shell.last_exit_status())
}
