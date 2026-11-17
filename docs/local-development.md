# Local development

Run the playground, PostgreSQL, all workspace CLIs, and real Bash terminal sessions
with the Python `sanctuary-dev` CLI. Each worktree gets its own Compose project and
Docker-assigned loopback port, so several checkouts can run concurrently.

## Start the stack

Install uv (version required by the root pyproject), and start a local Docker
engine with the Compose plugin and BuildKit. uv supplies the repository's Python
version and dependencies. Rust and frontend builds run inside Docker; the first
build needs network access and can take several minutes. Apple Silicon uses
Linux amd64 emulation to preserve the artifact validator's executable format.

From the checkout root:

```sh
uv run --locked sanctuary-dev up
```

The launcher prints every Compose command, streams build progress, waits for
healthy services, and prints `Ready: http://127.0.0.1:<assigned-port>/`. Open that
URL. The root redirects to the local preview with the command explorer and
terminal. Type `biggie --help` or choose a CLI in the sidebar.

Logs continue in the console. Ctrl+C stops following logs and leaves the stack
running. Stop and remove it with `uv run --locked sanctuary-dev down`. PostgreSQL uses temporary storage. Recreating its container discards preview data.
Recreating the playground starts fresh sessions. Session files use a private
Docker volume that supports Linux access ACLs, including Kara's atomic saves.
`down` removes that volume and this worktree's disposable data.

## Commands

Run these from the checkout root:

| Command | Effect |
| --- | --- |
| `uv run --locked sanctuary-dev up` | Build, start, wait for health, then follow logs |
| `uv run --locked sanctuary-dev start` | Build and start, then return after readiness |
| `uv run --locked sanctuary-dev up --detach` | Same as `start` |
| `uv run --locked sanctuary-dev start --no-build` | Start using existing images |
| `uv run --locked sanctuary-dev build` | Build images without starting containers |
| `uv run --locked sanctuary-dev logs` | Follow the last 100 lines and new logs |
| `uv run --locked sanctuary-dev logs --no-follow` | Print recent logs and return |
| `uv run --locked sanctuary-dev status` | Show this worktree's services, health, and ports |
| `uv run --locked sanctuary-dev url` | Print its currently assigned URL |
| `uv run --locked sanctuary-dev down` | Remove this worktree's containers and network |
| `uv run --locked sanctuary-dev config` | Inspect resolved Compose configuration; no daemon needed |
| `uv run --locked sanctuary-dev doctor` | Check Docker, show its context/version, and validate configuration |
| `uv run --locked sanctuary-dev --help` | List commands without requiring Docker |

`up` also accepts `--no-build`. Source files are copied into images; there is no
live reload or host source mount. After edits, run `start` again and reload the
browser using the printed URL. A recreated container may receive a different port.

For local CLI verification and reviewable WebM videos, follow the
[CLI recording guide](cli-development.md#record-a-visible-change).

## Multiple worktrees

Run `uv run --locked sanctuary-dev start` in each worktree. Project names contain the checkout
folder name and a hash of its canonical absolute path. Two folders named
`sanctuary` still get different networks, containers, images, and database data.
Repeated commands in one worktree operate on its existing project. Docker chooses
ports atomically when publishing containers; the launcher does not reserve ports
with a separate probe or maintain a state file.

The CLI can find the checkout from a subdirectory. To select another checkout
explicitly, put `--root` before the command:

```sh
uv run --locked sanctuary-dev --root /path/to/another/worktree status
```

Use a local Docker context: the printed loopback URL refers to the Docker host.
Before moving or deleting a worktree, run `down` there; its old absolute path is
part of its project identity. The launcher never removes other projects. Older
stacks named `sanctuary-playground-dev` are separate and are not automatically
stopped by this command.

## What runs

The [Python launcher](../tools/local-dev/src/local_dev/command.py) executes the
[Compose manifest](../tools/cli-playground/compose.dev.yml) with an explicit
project name and file path. `config` shows the resolved paths and services. There
are no hidden background launchers or host service installs.
The older `tools/dev.sh` entrypoint forwards arguments to this Python CLI.

The playground image builds the frontend and all Rust CLI binaries, generates
command metadata, migrates the development database, and publishes a local preview.
It uses the terminal transport test harness with real Bash PTYs. All sessions in
one worktree share a non-root container. Only the UI's dynamically assigned
loopback port is published; PostgreSQL is private to that Compose network.

This portable setup is for trusted local code and disposable data. It does not
run production Boxie sandbox isolation, gVisor, or Temporal. For those components,
use the native Linux setup below. Local previews have no merge-base comparison.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Docker is unreachable | Start the daemon and run `uv run --locked sanctuary-dev doctor`; check the active context |
| Unknown Compose option | Update the Compose plugin to support `up --wait` and `--wait-timeout` |
| Build fails | Read the streamed error, fix the source or dependency access, and rerun `start` |
| Health check fails | Startup prints service status and recent logs; use `logs` to investigate, then rerun `start` |
| Browser URL stopped working | Run `url`; container recreation can change the port |
| UI changes are missing | Run `start` to rebuild, wait for readiness, then reload |
| Need a clean environment | Run `down`, then `up`; development data will be discarded |

Failed startup leaves containers available for inspection. The CLI exits nonzero
on errors and returns 130 when interrupted. No arbitrary listener is killed to
make room for the stack.

## Work on a CLI or run checks on the host

Compose is sufficient for trying the UI and commands. For host development, install
Rust through rustup (the version is in [rust-toolchain.toml](../rust-toolchain.toml))
and uv for the Python workspace. Frontend checks additionally need Node and pnpm
matching [package.json](../tools/cli-playground/frontend/package.json).

Examples from the repository root:

```sh
cargo run -p echor -- hello
cargo test -p echor
uv sync --all-packages
pnpm --dir tools/cli-playground/frontend install --frozen-lockfile
pnpm --dir tools/cli-playground/frontend check
pnpm --dir tools/cli-playground/frontend test
pnpm --dir tools/cli-playground/frontend build
```

Run affected packages' checks directly. The playground browser integration suite
uses host port 8765 and a separate PostgreSQL test database. The worktree stack
uses a dynamically assigned port.

```sh
uv run --all-packages pytest -m integration \
  tools/cli-playground/tests/test_browser.py -q
```

Build the frontend before that browser test; it serves the compiled assets.
See the [playground guide](../tools/cli-playground/README.md#develop-the-service)
for terminal-specific testing and [repository instructions](../AGENTS.md) for
package verification requirements.

## Work on Boxie and the full service stack

For sandbox isolation, Temporal lifecycle, credentials, and production service
integration, use a disposable native Linux host with Docker and the `runsc`
runtime registered. Docker Desktop can build the images but does not validate
these production boundaries.

Start with [Boxie's native Linux setup](../packages/boxie/docs/deployment.md#configure-a-disposable-native-linux-host).
It covers private PostgreSQL and Temporal services, certificates, database
migrations, approved profiles, and separate API/supervisor configuration. Then
connect the [playground to that Boxie service](../tools/cli-playground/README.md#run-against-a-real-boxie-service)
with its own database and consumer credential. Those services use their own
Compose projects; `local-dev down` does not manage them.

This setup is deliberately separate from the portable playground shortcut: the
launcher does not silently replace gVisor with Docker's default runtime or claim
to exercise Temporal. Shared-host provisioning and releases remain in the
[infrastructure guide](../infra/README.md).
