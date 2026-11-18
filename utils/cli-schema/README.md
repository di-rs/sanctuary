# CLI schema

`cli-schema` exports a Sanctuary CLI's public Clap interface for the playground.
The [nested macro crate](macros/README.md) implements the `Schema` derive.
Apply it to the root parser struct.

```rust,no_run
use cli_schema::Schema;

#[derive(clap::Parser, Schema)]
struct Cli {}

fn main() -> std::process::ExitCode {
    Cli::run(|| {
        // Custom parsing, logging, and application work go here.
        std::process::ExitCode::SUCCESS
    })
}
```

Ordinary CLIs use `cli_log::run` or `cli_log::try_run`, which call this guard
before initializing logging or parsing arguments. Their `main` needs no schema
attribute or explicit check. Custom entrypoints use `Schema::run` around all
startup work, as above. The guard supports `ExitCode` and `Result<ExitCode, E>`;
errors from normal startup pass through unchanged. The derive declares support
but does not execute code by itself.

Argument-insensitive utilities derive `Schema` on a unit struct with
`#[schema(name = "true", about = "Exit with status 0")]` and use the same guard.
They export an empty interface without acquiring help or version flags.
The lower-level `emit` and `emit_empty` functions remain available.

Register shared executable checks in the package's `tests/cases.toml`:

```toml
schema = 1
binary = "example"
checks = ["help", "schema"]
```

Use only `checks = ["schema"]` for `true` and `false`, which have no help contract.
The [catalog harness](../../tools/cli-testing/docs/testing.md) runs these as named
executable tests. Command-specific assertions can use `assert_cli_schema` to
retrieve validated JSON; the generic Rust registration macro is no longer needed.

Run a built binary with `SANCTUARY_CLI_SCHEMA=1` and exactly `--help` to emit a
version 1 JSON document to stdout. Export succeeds with status 0; output errors
return status 1. Other invocations follow the normal CLI path. Export happens
before logging, input processing, or filesystem work.

The document contains the command tree, public aliases, descriptions, usage,
arguments, defaults, enum choices, value counts, and global argument ownership.
Short and full descriptions are separate (`about`/`long_about`, `help`/`long_help`).
Each argument retains its Clap ID, short/long spellings, public aliases, position,
requiredness, action and value labels. `owner` is the defining command path for a
global option, with an empty path for the root. `usage` is rendered for display;
`usage_override` distinguishes an explicitly authored usage string from generated
layout. `num_args.max: null` means unbounded arity.
Hidden entries and ambient environment values are omitted. This is a description
of the declared parser: it cannot describe arbitrary custom validation or changes
to runtime behavior. Consumers must validate documents from untrusted binaries.
