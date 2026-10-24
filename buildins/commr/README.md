# commr

`commr` compares two sorted text inputs and prints lines unique to either input or common to both.

## Arguments and options

| Argument or option | Meaning |
| --- | --- |
| `FILE_1 FILE_2` | Two required sorted inputs; at most one may be `-` for non-terminal stdin. |
| `-1` | Hide lines unique to the first input. |
| `-2` | Hide lines unique to the second input. |
| `-3` | Hide lines common to both inputs. |
| `-i, --insensitive` | Lowercase lines before comparison and output. |
| `-d, --output-delimiter TEXT` | Column separator; default tab. |
| `-h, --help` | Print help. |
| `-V, --version` | Print version. |

## Before using it

Reference: [GNU comm](https://www.gnu.org/software/coreutils/manual/html_node/comm-invocation.html).
Inputs must already be sorted using Rust string ordering, not locale collation;
there is no sortedness check. Case-insensitive mode changes the printed text.
Decoding, read, and output errors are reported on stderr with exit status 65.
Output already written before an error is retained; it is not a complete comparison.

## Test notes

Use BSD `comm` for the `-i` fixtures; GNU `comm` has no equivalent flag.
Generate with `LC_ALL=C` so collation matches the byte ordering used by the
committed inputs and `commr`. Custom-delimiter expectations replace reference
tabs locally.

## CLI test recipes

Native tests use `#[cli_test]` to receive shared helpers as `cx: &TestContext`.

Stable invocations and every retained expectation are connected in
[the catalog](tests/cases.toml). Boundary, error, and process scenarios remain in Rust.
The catalog replaces the Nushell generator; references use explicit macOS system
executables. Expected bytes are unchanged.

Run `cargo nextest run -p commr --profile ci` from the repository root.
Inspect recipes with `cli-testing --suite buildins/commr/tests/cases.toml explain NAME`.
Use the [fixture workflow](../../tools/cli-testing/README.md) to record independent
references and review changes before applying them. Ordinary tests only read
committed expectations.

[All commands](../../README.md)
