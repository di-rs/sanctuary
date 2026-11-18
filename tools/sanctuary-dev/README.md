# sdev

`sdev` runs Sanctuary's development tools from the current checkout. Install
the launcher with uv and Make, add the installation directory to your shell
path, then check a CLI.

```sh
make install-local
export PATH="$HOME/.local/bin:$PATH"
sdev check echor
```

Set `PREFIX=/path` when running Make to use another prefix. Without a global
installation, run `uv run --locked sdev` before the same arguments. The package
name is `sanctuary-dev`.

| Command | What it runs |
| --- | --- |
| `sdev check echor` | `cli-check verify echor` runs policy, formatting, Clippy and native tests. |
| `sdev test --suite buildins/echor/tests/cases.toml list` | `cli-testing` reads the package's fixture catalog. |
| `sdev bench buildins/echor/benches/cli-bench.toml --list` | `cli-bench` lists the benchmark suite's cases. |
| `sdev record echor no-newline` | `cli-record` films the selected demo for the PR. |
| `sdev local start` | `local-dev` starts the worktree playground. |
| `sdev check-pr --body-file pr.md` | `cli-check check-pr` checks the recording evidence in a PR description. |

Use `sdev COMMAND --help` for the delegate's options. Cargo runs the fixture
tool with the workspace lockfile, and uv selects the Python tools from the
workspace. The first invocation can build the Rust tool or install Python
dependencies.

Inside a worktree, relative paths start from the directory where you invoked
`sdev`. From elsewhere, `sdev --root /path/to/sanctuary COMMAND` runs from
that checkout's root. See the [CLI development guide](../../docs/cli-development.md)
for toolchain setup and the [standalone tool index](../../README.md#development-tools)
for each command's documentation.
