# echor

`echor` prints its text arguments separated by spaces.

## Arguments and options

| Argument or option | Meaning |
| --- | --- |
| `TEXT...` | One or more required text arguments, joined with spaces. |
| `-n` | Omit the final newline. |
| `--` | End option parsing so later arguments may start with a hyphen. |
| `-h, --help` | Print help. |
| `-V, --version` | Print version. |

## Before using it

Reference: [GNU echo](https://www.gnu.org/software/coreutils/manual/html_node/echo-invocation.html).
At least one text argument is required. There is no escape-sequence interpretation
or `-e`/`-E` option; this is not a replacement for shell-specific `echo` behavior.

## Test notes

The generator uses an external `echo`; choose the reference executable through
`PATH` rather than relying on a shell builtin. The `-n` fixtures intentionally
have no final newline.

## CLI test recipes

Native tests use `#[cli_test]` to receive shared helpers as `cx: &TestContext`.

Stable invocations and every retained expectation are connected in
[the catalog](tests/cases.toml). Boundary, error, and process scenarios remain in Rust.
The catalog replaces the Nushell generator; references use explicit macOS system
executables. Expected bytes are unchanged.

Run `cargo nextest run -p echor --profile ci` from the repository root.
Inspect recipes with `cli-testing --suite buildins/echor/tests/cases.toml explain NAME`.
Use the [fixture workflow](../../tools/cli-testing/README.md) to record independent
references and review changes before applying them. Ordinary tests only read
committed expectations.

[All commands](../../README.md)
