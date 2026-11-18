# Develop a Sanctuary CLI

A Sanctuary CLI is a standalone Cargo binary that people can run from a shell.
The playground is one consumer of that binary. Keep argument parsing, exit
status, file handling and stdout usable without the playground or Boxie.

## Set up a checkout

Install Git, rustup, uv, prek and cargo-nextest. Cargo selects the toolchain in
[rust-toolchain.toml](../rust-toolchain.toml). Prepare the development command and
Git hooks from the checkout root.

```sh
uv sync --locked --all-packages
prek install
. .venv/bin/activate
```

To record a demo, start Docker with Compose and BuildKit and install the
frontend's versions of Node and pnpm. Then prepare Chromium.

```sh
pnpm --dir tools/cli-playground/frontend install --frozen-lockfile
pnpm --dir tools/cli-playground/frontend exec playwright install chromium
sdev local doctor
```

On Linux, `playwright install --with-deps chromium` also installs the browser's
system dependencies. The [local development guide](local-development.md) covers
starting a persistent playground and inspecting a worktree's services.

## Add a command

1. Pick the observable contract and an independent reference. Define arguments,
   stdin, stdout, stderr, status and file effects. For a compatibility claim,
   name the implementation and platform that produced the expected behavior.
2. Add a Cargo package under `buildins/` for a standalone utility, or `packages/`
   for an application. Cargo discovers crates under both directories by glob.
   The root manifest excludes Python-only services under `packages/`. Update
   the lockfile for the new crate. Give the directory,
   package and single `src/main.rs` binary the same name. Inherit the
   workspace lints. A library target in the same crate can expose an API.
3. Add `cli-schema.workspace = true` under `[dependencies]` and export the
   actual parser through [cli-schema](../utils/cli-schema/README.md).
   Use [cli-log](../utils/cli-log/README.md) when the command needs structured
   logging. Keep stdout available to pipelines. Share library code when two
   commands have the same contract, including errors and byte handling.
4. Add `cli-testing` as a workspace development dependency and register behavioral
   tests in `tests/cli.rs`. The [test authoring guide](../tools/cli-testing/docs/testing.md)
   covers independent byte fixtures, declarative cases and interactive scenarios.
   [catr](../buildins/catr/README.md) has both catalog and native tests.
5. Give the package a README with its name as the title, a short purpose, and a
   runnable shell example in the first section. Describe the result and document
   flags, exit behavior and limitations where readers need them. Run
   `uv run --locked sdev index` and commit the refreshed
   [command index](../README.md#commands). The table uses Cargo’s package
   description or, when it is empty, the README’s opening paragraph. Refresh it
   after moving or removing a CLI or editing its listed purpose. Applications in `packages/` also
   have a `docs/architecture.md`. Keep agent instructions in `AGENTS.md` and skills.
6. Add a package-owned [benchmark suite](../tools/cli-bench/README.md) or document
   a finite-benchmark exemption in the manifest. Add browser examples beside the
   native tests, then run the checks below.

## Verify a change

From the activated checkout, check the CLI you changed.

```sh
sdev check echor
```

This runs package policy, formatting, Clippy and native tests on your working
tree. Without activating the environment, use `uv run --locked sdev
check echor`. For shared changes, test affected consumers as well. Run
`cargo test --locked -p PACKAGE --all-features --doc` for a library target.
For a case catalog, run `sdev test --suite
buildins/catr/tests/cases.toml validate` with the owning catalog path.
Automatic reference comparison additionally requires the declared reference
platform and executable.

Use `uv run --locked cli-check` for workspace policy. For workflow edits, run
`actionlint` and `zizmor --offline --no-progress --collect workflows actions -- .github`.
Run `lychee --offline --include-fragments=anchor-only -- FILES` and
`typos --force-exclude -- FILES` on changed Markdown. A real commit runs the
configured Git hooks. Linux, macOS and hosted-only checks report on the PR.

## Record a visible change

Choose the smallest example that shows what a reviewer should notice. A new
flag, changed output, or a new subcommand usually needs one invocation. A shared
change can use one representative consumer. An internal refactor needs only
its native checks and a short explanation in the PR.

Keep reusable demos in the CLI's `tests/browser.toml`. Each `[[cases]]` entry
has a unique name and an argument array, using the same TOML convention as
native cases. For example, echor can print text without a trailing newline.

```toml
[[cases]]
name = "no-newline"
args = ["-n", "--", "hello", "sanctuary"]
```

List the names, then record only the demo you want to show.

```sh
sdev record echor --list
sdev record echor no-newline
```

Pass additional names in the order they should appear in the same video.
Playwright runs the working-tree binary in a disposable local Bash terminal and
prints the WebM directory under `target/cli-recordings/`. Use `--output DIR` to
choose a new directory. Open the video and verify that the change is visible
and the result legible before uploading.

A case can provide `stdin`, a shell `setup` before the invocation or an `after`
command to show its effect. For interactive programs, `ready` waits for text
before `keys` sends keystrokes. Supply synthetic inputs suitable for a public
PR. Keep expected output, file assertions, failure cases and alias coverage
in the native tests. See the [editor demo](../packages/kara/tests/browser.toml).

## Attach a demo to the pull request

In GitHub, edit the PR description. Under **Testing/Validation**, add a level-four
heading with the CLI name in backticks, as in the example below. Leave a blank
line and drag the WebM onto the next line. Wait for the attachment URL and save
the description. The browser upload works independently of your installed
GitHub CLI version. [GitHub's file attachment guide](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/attaching-files)

For a terminal upload, the following procedure was verified with GitHub CLI
2.104.0. Look for attachment reference rewriting in `gh pr edit --help`.
Save the current PR body alongside the recording, then add the following
snippet under **Testing/Validation**. The file path is relative to the body file.

```markdown
#### `echor`

![](./commands-echor/video.webm)
```

```sh
gh pr edit PR_NUMBER --body-file pr.md --attach ./commands-echor/video.webm
```

The **Local CLI recordings** check inspects the published PR description on
creation, pushes and edits. For each CLI with a direct source or build-script
change, attach its local video or put `Internal change — REASON` on the line
beneath its heading and explain why the behavior is unchanged. For a visible
shared-library change, attach a representative consumer demo. CI runs native
tests and browser UI regressions. Contributors choose and record demos locally.

To run the same description check from the checkout, use the PR's base branch
and current body.

```sh
gh pr view PR_NUMBER --json body --jq .body > pr.md
sdev check-pr --base origin/master --body-file pr.md
```
