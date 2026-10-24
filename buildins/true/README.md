# true

`true` exits with status 0 and produces no output.

| Argument or option | Meaning |
| --- | --- |
| Any arguments | Ignored, including `--help` and `--version`; status remains 0. |

Reference: [GNU true](https://www.gnu.org/software/coreutils/manual/html_node/true-invocation.html).
## CLI test recipes

Native tests use `#[cli_test]` to receive shared helpers as `cx: &TestContext`.

The fixed silent-status contract lives in [the catalog](tests/cases.toml),
with independently specified POSIX expectations. Native Rust tests retain argument handling.

Run `cargo nextest run -p true --profile ci` from the repository root.
Inspect recipes with `cli-testing --suite buildins/true/tests/cases.toml explain NAME`.
Use the [fixture workflow](../../tools/cli-testing/README.md) to record independent
references and review changes before applying them. Ordinary tests only read
committed expectations.

[All commands](../../README.md)
