# touchr

`touchr` creates missing files and sets file modification times.

## Arguments and options

| Argument or option | Meaning |
| --- | --- |
| `FILES...` | One or more required paths; create missing files and update modification times. |
| `-c` | Do not create missing files. |
| `-t TIMESTAMP` | UTC `YYYYMMDDhhmm` or `YYYYMMDDhhmmss`; default current time. |
| `-h, --help` | Print help. |
| `-V, --version` | Print version. |

## Before using it

Reference: [GNU touch](https://www.gnu.org/software/coreutils/manual/html_node/touch-invocation.html).
Only modification time is explicitly set, not access time. The supported timestamp
forms are `YYYYMMDDhhmm` and `YYYYMMDDhhmmss`, interpreted as UTC. No local-time parsing, reference-file option,
or separate access-time mode is implemented.

## CLI test recipes

Native tests use `#[cli_test]` to receive shared helpers as `cx: &TestContext`.

The basic creation contract is a Rust-owned [catalog case](tests/cases.toml)
connected with `#[test_case]`. Its body creates an isolated workspace, runs once,
and verifies the filesystem result; the wrapper checks status and both streams.
Multi-command, timestamp, logging, and failure scenarios remain ordinary Rust tests
using shared workspaces. The mutation recipe has manual expectations and runs through native tests.

Run `cargo nextest run -p touchr --profile ci` from the repository root.
Inspect recipes with `cli-testing --suite buildins/touchr/tests/cases.toml explain NAME`.
Use the [fixture workflow](../../tools/cli-testing/README.md) to record independent
references and review changes before applying them. Ordinary tests only read
committed expectations.

[All commands](../../README.md)
