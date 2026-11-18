# true

`true` exits with status 0 and produces no output.

## Read the exit status

From the repository root:

<!-- cli-example -->

```sh
cargo run -q -p true --
```

The command exits with status 0. Run `printf '%s\n' "$?"` immediately afterward
to display `0`.

## Arguments and options

| Argument or option | Meaning |
| --- | --- |
| Any arguments | Ignored, including `--help` and `--version`; status remains 0. |

Reference: [GNU true](https://www.gnu.org/software/coreutils/manual/html_node/true-invocation.html).
[All commands](../../README.md)
