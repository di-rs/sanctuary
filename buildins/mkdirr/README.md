# mkdirr

`mkdirr` creates directories, including missing parent directories by default.

## Arguments and options

| Argument or option | Meaning |
| --- | --- |
| `DIRS...` | One or more required directory paths. |
| `-p` | Create missing parents; already enabled by default. |
| `-h, --help` | Print help. |
| `-V, --version` | Print version. |

Existing directories are accepted. Existing files or creation failures stop the command with an error.

## Before using it

Unlike [GNU mkdir](https://www.gnu.org/software/coreutils/manual/html_node/mkdir-invocation.html),
parent creation needs no `-p`. No permission-mode option is implemented.
At least one directory path is required.

## CLI test recipes

The basic creation contract is a Rust-owned [catalog case](tests/cases.toml)
connected with `#[test_case]`. Its body creates an isolated workspace, runs once,
and verifies the filesystem result; the wrapper checks status and both streams.
Multi-command, timestamp, logging, and failure scenarios remain ordinary Rust tests
using shared workspaces. The mutation recipe has manual expectations and runs through native tests.

Run `cargo nextest run -p mkdirr --profile ci` from the repository root.
Inspect recipes with `cli-testing --suite buildins/mkdirr/tests/cases.toml explain NAME`.
Use the [fixture workflow](../../tools/cli-testing/README.md) to record independent
references and review changes before applying them. Ordinary tests only read
committed expectations.

[All commands](../../README.md)
