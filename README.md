# Sanctuary

![Source nonblank lines](https://raw.githubusercontent.com/di-rs/sanctuary/chore/badges/loc.svg)

Sanctuary is a platform for shell sandboxes, with Rust command-line tools, shared
libraries, and Python services. Each CLI is its own Cargo package.
Python services and repository tools share a uv workspace.

## Try a command

From the repository root with the pinned Rust toolchain installed:

```sh
cargo run -p echor -- hello world
```

Run `make install-local` to put `sdev` in `~/.local/bin`. Add that directory to
`PATH`, or set `PREFIX=/path` to use another prefix. From a checkout,
`sdev check echor` runs package policy and native tests. The
[development launcher](tools/sanctuary-dev/README.md) also opens the fixture,
benchmark, recording and playground tools.

Choose another package from the tables below. These commands implement selected
behaviors, not complete GNU/BSD replacements; each README explains the differences.

For Python tools, install the workspace dependencies with
`uv sync --all-packages`, then run commands through `uv run`.
Frontend development has its own prerequisites in the playground guide.

## Try the browser playground

Open a pull request's playground link to try its commands without building them
locally. The [playground guide](tools/cli-playground/README.md#use-a-preview)
explains sessions, sample files, and switching builds.

To run the playground and all CLIs locally with Docker Compose:

```sh
uv run --locked sdev local up
```

The [local development guide](docs/local-development.md) covers setup, console
output, rebuilding, shutdown, and the separate full Boxie service setup.

## Applications

[Boxie](packages/boxie/README.md) runs isolated sandboxes through a private
service API. The [command index](#commands) includes the Rust applications.

## Commands

<!-- BEGIN generated CLI index -->

| Command | Purpose |
| --- | --- |
| [biggie](packages/biggie/README.md) | A tool to generate large files |
| [calr](buildins/calr/README.md) | calr prints a month or year as a Sunday-first text calendar. |
| [catr](buildins/catr/README.md) | catr concatenates UTF-8 text files or piped input to standard output. |
| [cli-testing](tools/cli-testing/README.md) | Shared process setup and byte-exact fixtures for CLI integration tests |
| [commr](buildins/commr/README.md) | commr compares two sorted text inputs and prints lines unique to either input or common to both. |
| [cutr](buildins/cutr/README.md) | cutr selects fields, Unicode characters, or bytes from text input. |
| [echor](buildins/echor/README.md) | echor prints its text arguments separated by spaces. |
| [false](buildins/false/README.md) | false exits with status 1 and produces no output. |
| [findr](buildins/findr/README.md) | findr recursively lists paths filtered by entry type and filename regular expressions. |
| [grepr](buildins/grepr/README.md) | A tool to search files |
| [headr](buildins/headr/README.md) | headr prints the beginning of files or piped input. |
| [kara](packages/kara/README.md) | A small modal terminal text editor |
| [lsr](buildins/lsr/README.md) | lsr lists files and immediate directory contents on Unix systems. |
| [mkdirr](buildins/mkdirr/README.md) | mkdirr creates directories, including missing parent directories by default. |
| [parsu](packages/parsu/README.md) | Simple XML parser with combinators |
| [pwdr](buildins/pwdr/README.md) | pwdr prints the current working directory as an absolute path. |
| [shish](packages/shish/README.md) | Sanctuary shell |
| [tailr](buildins/tailr/README.md) | tailr prints the end of files or stdin, or their contents starting at a chosen line or byte. |
| [touchr](buildins/touchr/README.md) | touchr creates missing files and sets file modification times. |
| [true](buildins/true/README.md) | true exits with status 0 and produces no output. |
| [uniqr](buildins/uniqr/README.md) | uniqr collapses consecutive runs of matching text lines. |
| [wcr](buildins/wcr/README.md) | wcr counts lines, words, characters, and bytes in UTF-8 text. |

<!-- END generated CLI index -->

## Development tools

| Project                                          | Purpose                                                                            |
| ------------------------------------------------ | ---------------------------------------------------------------------------------- |
| [sdev](tools/sanctuary-dev/README.md)            | Launch development tools from the active checkout                                  |
| [cli-record](tools/cli-record/README.md)         | Record selected CLI demos in a disposable browser playground                       |
| [local-dev](tools/local-dev/README.md)           | Build and manage a worktree’s local playground stack                               |
| [cli-bench](tools/cli-bench/README.md)           | Run per-CLI benchmark suites with Biggie and hyperfine                             |
| [cli-check](tools/cli-check/README.md)           | Check CLI package boundaries, tests, documentation, and benchmark coverage         |
| [cli-playground](tools/cli-playground/README.md) | Try Rust CLIs in a browser terminal with disposable files and a preview URL per PR |

## Shared libraries

| Project                            | Purpose                                            |
| ---------------------------------- | -------------------------------------------------- |
| [cli-log](utils/cli-log/README.md) | Shared structured file logging and error reporting |
| [cli-schema](utils/cli-schema/README.md) | Export a CLI's parser for the playground |
| [cli-testing](tools/cli-testing/docs/testing.md) | Shared CLI test setup and byte fixture loading |

## Find your way around

The [architecture overview](docs/architecture.md) explains how commands, the playground,
and Boxie fit together. The [platform direction](docs/platform-direction.md)
describes the durable-shell north star and open design questions. The
[threat model](docs/thread-model.md) describes security boundaries.

To inspect production dashboards and workflows from local Codex Desktop or CLI,
see [Debug production with Codex and MCP](docs/production-mcp.md).

| Directory   | Contents                                              |
| ----------- | ----------------------------------------------------- |
| `buildins/` | Small standalone Rust CLIs                            |
| `packages/` | Larger applications and Boxie                         |
| `utils/`    | Shared Rust libraries                                 |
| `tools/`    | Repository checks, benchmarks, and browser playground |
| `infra/`    | Host provisioning and service composition             |

## Try the browser playground

Open a pull request's playground link to try its commands without building them
locally. The [playground guide](tools/cli-playground/README.md#use-a-preview)
explains sessions, sample files, and switching builds.

## Make a change

The [CLI development guide](docs/cli-development.md) covers package layout,
test fixtures, local checks and browser recordings for pull requests.
Deployment instructions live in the [shared-host guide](infra/README.md).
See [dependency maintenance](docs/dependency-updates.md) for automated coverage
and pins that need manual updates.

Licensed under [Apache-2.0](LICENSE). Preserve tutorial credits in package READMEs.
