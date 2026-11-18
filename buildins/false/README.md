# false

`false` exits with status 1 and produces no output.

## Read the exit status

From the repository root:

```sh
cargo run -q -p false
printf '%s\n' "$?"
```

The second command prints `1`.

## Arguments and options

| Argument or option | Meaning |
| --- | --- |
| Any arguments | Ignored, including `--help` and `--version`; status remains 1. |

Reference: [GNU false](https://www.gnu.org/software/coreutils/manual/html_node/false-invocation.html).
[All commands](../../README.md)
