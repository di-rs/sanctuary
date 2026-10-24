# pwdr

`pwdr` prints the current working directory as an absolute path.

## Arguments and options

| Argument or option | Meaning |
| --- | --- |
| `-L` | Logical path, preserving valid `PWD` symlinks; default mode. |
| `-P` | Physical path with symlinks resolved; conflicts with `-L`. |
| `-h, --help` | Print help. |
| `-V, --version` | Print version. |

Logical mode falls back to the OS-reported directory when `PWD` is invalid.

## Before using it

Reference: [GNU pwd](https://www.gnu.org/software/coreutils/manual/html_node/pwd-invocation.html).
This implementation defaults to logical mode, unlike standalone GNU `pwd`'s
usual physical default. `-L` and `-P` are mutually exclusive rather than using
the last flag supplied. Paths containing non-Unicode bytes are displayed lossily.

## CLI test structure

Native tests use `#[cli_test]` to receive shared helpers as `cx: &TestContext`.

Current-directory, PWD fallback, and symlink scenarios remain native Rust
tests because their expected paths are generated inside temporary workspaces.
All scenarios now share deterministic command defaults and isolated workspaces;
explicit PWD manipulation and exact path assertions remain visible.

Run `cargo nextest run -p pwdr --profile ci`. The
[shared Rust testing helpers](../../tools/cli-testing/docs/testing.md) provide
command defaults and isolated workspaces without hiding filesystem assertions.

[All commands](../../README.md)
