# Develop a Sanctuary CLI

A Sanctuary CLI is a standalone Cargo binary that people can run from a shell.
The playground is one consumer of that binary. Keep argument parsing, exit
status, file handling and stdout usable without the playground or Boxie.

## Set up a checkout

Install Git, rustup, uv, prek and cargo-nextest. Cargo selects the toolchain in
[rust-toolchain.toml](../rust-toolchain.toml). For browser recordings, start Docker
with Compose and BuildKit and install the frontend's versions of Node and pnpm.
From the checkout root, prepare the Python tools, Git hooks and browser once:

```sh
uv sync --locked --all-packages
prek install
pnpm --dir tools/cli-playground/frontend install --frozen-lockfile
pnpm --dir tools/cli-playground/frontend exec playwright install chromium
uv run --locked local-dev doctor
```

On Linux, `playwright install --with-deps chromium` also installs the browser's
system dependencies. The [local development guide](local-development.md) covers
starting a persistent playground and inspecting a worktree's services.

## Add a command

1. Pick the observable contract and an independent reference. Define arguments,
   stdin, stdout, stderr, status and file effects. For a compatibility claim,
   name the implementation and platform that produced the expected behavior.
2. Add a Cargo package under `buildins/` for a standalone utility, or `packages/`
   for an application. Builtins are workspace members by glob. Register other
   packages in the root manifest and update the lockfile. Give the directory,
   package and single `src/main.rs` binary the same name. Inherit the workspace
   lints. A library target in the same crate can expose an API.
3. Export the actual parser through [cli-schema](../utils/cli-schema/README.md).
   Use [cli-log](../utils/cli-log/README.md) when the command needs structured
   logging. Keep stdout available to pipelines. Share library code when two
   commands have the same contract, including errors and byte handling.
4. Add `cli-testing` as a workspace development dependency and register behavioral
   tests in `tests/cli.rs`. The [test authoring guide](../tools/cli-testing/docs/testing.md)
   covers independent byte fixtures, declarative cases and interactive scenarios.
   [catr](../buildins/catr/README.md) has both catalog and native tests.
5. Give the package a README with its name as the title, a short purpose, and a
   runnable shell example in the first section. Describe the result and document
   flags, exit behavior and limitations where readers need them. Link it from the
   [root index](../README.md). Applications in `packages/` also have a
   `docs/architecture.md`. Keep agent instructions in `AGENTS.md` and skills.
6. Add a package-owned [benchmark suite](../tools/cli-bench/README.md) or document
   a finite-benchmark exemption in the manifest. Add browser examples beside the
   native tests, then run the checks below.

## Verify a change

For example, verify echor from the repository root:

```sh
make check-cli CLI=echor
```

This runs CLI policy, formatting, Clippy and native tests, then builds the current
checkout in Docker and runs its browser examples. It prints the directory with
the WebM recordings. For shared changes, test affected consumers as well. Run
`cargo test --locked -p PACKAGE --all-features --doc` for a library target.
For a case catalog, run `cargo run --locked -p cli-testing -- --suite
buildins/catr/tests/cases.toml validate` with the owning catalog path.
Automatic reference comparison additionally requires the declared reference
platform and executable.

Use `uv run --locked cli-check` for workspace policy. For workflow edits, run
`actionlint` and `zizmor --offline --no-progress --collect workflows actions -- .github`.
Run `lychee --offline --include-fragments=anchor-only -- FILES` and
`typos --force-exclude -- FILES` on changed Markdown. A real commit runs the
configured Git hooks. Linux, macOS and hosted-only checks report on the PR.

## Record the public flags

Keep small examples in the CLI's `tests/browser.json`. Each case contains an
argument array in invocation order. Use separate option and value tokens and
put subcommand names first. Give an expected output substring, file assertion or
exit status for the behavior under test. The default expected exit status is zero.

```json
{
  "cases": [
    {"args": ["-n", "--", "hello sanctuary"], "contains": "hello sanctuary"}
  ]
}
```

The recorder reads the schema exported by the built binary, exercises the short,
long and visible alias spellings, and runs help and version where advertised.
Give mutually exclusive flags separate examples. A new option or subcommand
without a behavioral example fails the check. Native tests own byte-for-byte
comparison, error paths and platform-specific behavior.

Each video uses the real playground, Bash PTY and CLI in a fresh session.
Examples can supply `stdin`, an expected `exit`, or a shell `check` for file
effects. For an interactive command, `ready` waits for terminal output before
`keys` sends Playwright key presses. A recipe can use `setup` to create disposable
inputs. Use synthetic data suitable for a public PR. See the
[editor example](../packages/kara/tests/browser.json) and the
[fixture tool example](../tools/cli-testing/tests/browser.json).

```sh
uv run --locked local-dev record -p echor -p catr
uv run --locked local-dev record --base origin/master --head HEAD --list
```

Named packages include uncommitted edits. Revision selection compares commits
with their merge base. Use `--all` for the complete inventory. A recording run
uses its own Compose project and removes its session volume on exit. It writes
videos under `target/cli-recordings/`; `--output` selects a new directory.

On a ready PR, CI repeats the affected browser checks against the PR head in
groups of up to eight CLIs, with four groups running concurrently. Each
**CLI browser recordings** check links its downloadable videos in the job
summary. Link that artifact under **Testing/Validation** in the PR and report
the local run. GitHub retains CI videos for 14 days. To share the exact local
capture, attach the WebM from the printed directory to the PR in GitHub.
