# uniqr

`uniqr` collapses consecutive runs of matching text lines.

## Arguments and options

| Argument or option | Meaning |
| --- | --- |
| `FILE` | Input file; default `-` reads non-terminal stdin. |
| `OUTPUT_FILE` | Optional output file; default stdout. Existing output files are truncated. |
| `-c, --count` | Prefix each retained line with its consecutive run length. |
| `-h, --help` | Print help. |
| `-V, --version` | Print version. |

## Before using it

Reference: [GNU uniq](https://www.gnu.org/software/coreutils/manual/html_node/uniq-invocation.html).
Comparisons ignore the terminating newline but preserve spaces, tabs, and carriage
returns. Output keeps the first line of each run unchanged. Input must be UTF-8; all runs are stored in
memory before output. Only adjacent matches are collapsed. Output files are
truncated. Input/output aliases, including hard links and symlinks, are rejected
before truncation with status 65; the original input remains intact.

## Test notes

Use BSD `uniq` for the existing fixtures: it preserves an unterminated final
record and formats counts in four columns. GNU `uniq` adds a final newline in
those cases and uses seven-column counts. Preserve the committed line endings
and count spacing.

## CLI test recipes

File and stdin fixture cases live in [the catalog](tests/cases.toml).
Output-file, alias-safety, and error scenarios remain in Rust and share the same
committed expectations. Explicit BSD uniq recipes replace the Nushell generator;
input bytes, unterminated records, and count spacing are preserved.

Run `cargo nextest run -p uniqr --profile ci` from the repository root.
Inspect recipes with `cli-testing --suite buildins/uniqr/tests/cases.toml explain NAME`.
Use the [fixture workflow](../../tools/cli-testing/README.md) to record independent
references and review changes before applying them. Ordinary tests only read
committed expectations.

[All commands](../../README.md)
