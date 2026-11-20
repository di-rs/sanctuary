use anyhow::{Context, Result};
use biggie::{generate_bytes, generate_fields, generate_records, generate_text};
use serde_json::{Value, json};
use std::{io::BufWriter, path::Path, process::ExitCode};
mod cli;
mod output;
use cli::{Cli, Command, ParsedCli};
fn main() -> ExitCode {
    <Cli as cli_schema::Schema>::run(|| {
        let cli = match Cli::parse_validated() {
            Ok(cli) => cli,
            Err(error) => {
                let session = if matches!(
                    error.kind(),
                    clap::error::ErrorKind::DisplayHelp | clap::error::ErrorKind::DisplayVersion
                ) {
                    cli_log::init_with_level("biggie", log::LevelFilter::Off)
                } else if let Some(level) = Cli::error_log_level() {
                    cli_log::init_with_level("biggie", level)
                } else {
                    cli_log::init("biggie")
                };
                if error.exit_code() != 0
                    && std::env::args_os()
                        .skip(1)
                        .take_while(|a| a != "--")
                        .any(|a| a == "--json")
                {
                    let _ = emit_json(
                        &serde_json::json!({"ok": false, "error": {"kind": "arguments", "message": error.to_string()}}),
                    );
                    return session.finish(2);
                }
                return session.clap_error(&error);
            }
        };
        let session = cli_log::init_with_level("biggie", cli.logging.level());
        let status = match execute(&cli) {
            Ok(()) => 0,
            Err(error) => {
                if cli.json {
                    cli_log::record_error(format_args!("{error:#}"));
                    let _ = emit_json(
                        &serde_json::json!({"ok": false, "error": {"kind": "operation", "message": format!("{error:#}")}}),
                    );
                } else {
                    cli_log::diagnostic!("biggie: {error:#}");
                }
                1
            }
        };
        session.finish(status)
    })
}
fn execute(cli: &ParsedCli) -> Result<()> {
    match &cli.command {
        Command::Text(args) => {
            let options = args.options();
            execute_single(
                cli,
                "text",
                &args.file,
                options.generation.lines,
                ("line", "records"),
                |writer| generate_text(writer, &options),
            )
        }
        Command::Records(args) => {
            let options = args.options().context("Cannot load record corpus")?;
            if args.file.as_os_str() != "-"
                && let Some(input) = &args.records_file
            {
                output::reject_alias(input, &args.file)?;
            }
            execute_single(
                cli,
                "records",
                &args.file,
                options.total_records()?,
                ("record", "records"),
                |writer| generate_records(writer, &options),
            )
        }
        Command::Fields(args) => {
            let options = args.options();
            execute_single(
                cli,
                "fields",
                &args.file,
                options.lines,
                ("record", "records"),
                |writer| generate_fields(writer, &options),
            )
        }
        Command::Bytes(args) => {
            let options = args.options();
            execute_single(
                cli,
                "bytes",
                &args.file,
                options.bytes,
                ("byte", "bytes"),
                |writer| generate_bytes(writer, &options),
            )
        }
        Command::Pair(args) => {
            let options = args.options();
            if cli.dry_run {
                output::reject_alias(&args.left, &args.right)?;
            } else {
                output::pair(&args.left, &args.right, &options, !cli.json)?;
            }
            emit_plan(cli, "pair", || {
                let (left, right) = options.record_counts()?;
                Ok(vec![
                    describe_output(&args.left, left, "records"),
                    describe_output(&args.right, right, "records"),
                ])
            })
        }
    }
}

fn execute_single(
    cli: &ParsedCli,
    operation: &str,
    path: &Path,
    count: u64,
    (completion_unit, plan_unit): (&str, &str),
    generate: impl FnOnce(&mut BufWriter<output::Destination>) -> Result<()>,
) -> Result<()> {
    if !cli.dry_run {
        anyhow::ensure!(
            !cli.json || path.as_os_str() != "-",
            "--json requires named outputs or --dry-run; stdout is reserved for generated data"
        );
        output::single(path, count, completion_unit, !cli.json, generate)?;
    }
    emit_plan(cli, operation, || {
        Ok(vec![describe_output(path, count, plan_unit)])
    })
}

fn describe_output(path: &Path, count: u64, unit: &str) -> Value {
    json!({"path": path.to_string_lossy(), "count": count, "unit": unit})
}

fn emit_plan(
    cli: &ParsedCli,
    operation: &str,
    outputs: impl FnOnce() -> Result<Vec<Value>>,
) -> Result<()> {
    if !cli.dry_run && !cli.json {
        return Ok(());
    }
    let plan = json!({"operation": operation, "dry_run": cli.dry_run, "outputs": outputs()?});
    if cli.json {
        emit_json(&json!({"ok": true, "data": plan}))
    } else {
        emit_json(&plan)
    }
}

fn emit_json(value: &Value) -> Result<()> {
    use std::io::Write;
    let mut stdout = std::io::stdout().lock();
    serde_json::to_writer(&mut stdout, value)?;
    writeln!(stdout)?;
    stdout.flush()?;
    Ok(())
}
