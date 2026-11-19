# Local development

Use `sdev local` to run the CLI playground from your checkout with portable
Bash terminals or with Boxie. Each worktree has its own projects and
Docker-assigned loopback ports.

## Try a preview on Docker Desktop

Install uv and start a local Docker engine with Compose and BuildKit. Run the
launcher from the checkout root.

```sh
uv run --locked sdev local up
```

Open the playground URL printed after `Ready` and try `echor hello`. The launcher
reports `Terminal backend: portable Bash PTYs`. The preview includes workspace
CLIs and their command catalogs. Sessions run in one non-root development
container for trusted local code. Apple Silicon runs the preview image under
Linux amd64 emulation to match the executable format used by Boxie.

Ctrl+C stops following logs. Run `uv run --locked sdev local down` to remove
this worktree's playground, PostgreSQL, network and disposable data.

## Start Boxie on Linux

On a native Linux/amd64 development host, install OpenSSL and rootful Docker
Engine with Compose and BuildKit. Register gVisor as the `runsc` runtime.
The launcher uses the local `/var/run/docker.sock` with host UID mapping, and
the supervisor requires access to that socket. Verify the runtime and Compose
configuration first.

```sh
uv run --locked sdev local doctor --mode boxie
uv run --locked sdev local start --mode boxie
```

The Boxie project starts PostgreSQL, Temporal, the API and the supervisor.
It builds the service and shipped sandbox image and initializes the schemas,
Temporal namespace and development credentials. The launcher prints the
loopback API URL and path to its consumer credential. Only the supervisor
receives the Docker socket. Use `down --mode boxie` to remove this project's
containers, networks, database volume, local credentials and sandbox data.
Use the same local Docker engine for teardown. If the engine changes or its
identity cannot be checked, the launcher keeps the local state.

To start both projects and connect the browser to the local Boxie API, run:

```sh
uv run --locked sdev local start --mode full
```

Open the playground URL printed after `Terminal backend: Boxie API`. Terminals
now run in Boxie-managed gVisor sandboxes. The playground brings its own
PostgreSQL and joins only Boxie's consumer network. Run `down --mode full` to
stop the playground before tearing down its Boxie project.

## Connect the playground to a development Boxie

Obtain a private API origin reachable **from the playground container** and the
corresponding consumer credential from the development Boxie operator. Use HTTPS
when sending the credential across hosts. Save the token in a private regular
file with mode `0600`.

```sh
export LOCAL_DEV_BOXIE_URL=https://boxie.dev.example
export LOCAL_DEV_BOXIE_CREDENTIAL_FILE="$HOME/.config/boxie/development.secret"
uv run --locked sdev local start --mode external
```

Startup publishes the checkout's binaries and catalog through the development
Boxie and prints `Terminal backend: Boxie API`. The playground has its own
database. Its credential is copied into a worktree-owned volume. Run
`uv run --locked sdev local down --mode external` to remove that project's
containers, networks, volumes and local copy of the credential. The development
Boxie and other worktrees continue running.

Before removing its local data, `down` stops sessions and retires artifacts for
every preview recorded by this worktree. If Boxie has yet to acknowledge
cleanup, the command exits nonzero and keeps the project's containers,
database and volumes. Restore connectivity and retry `down`. The playground
blocks new sessions and publications while teardown is pending. Keep the
original endpoint and credential until cleanup finishes. Manually removing
the development PostgreSQL container discards its in-memory database and the
records needed to retry cleanup.

## Commands

Run from the checkout root with `uv run --locked sdev local COMMAND`. Commands
accept `--mode portable|boxie|full|external`. The default is `portable`.

| Command | Effect |
| --- | --- |
| `up` | Build, start, wait for readiness and follow logs. In full mode, follows the playground logs. |
| `start`, `up --detach` | Build and start, then return after readiness. |
| `start --no-build`, `up --no-build` | Start using existing worktree images. |
| `build` | Build the selected images. |
| `logs --no-follow` | Print recent logs and return. Omit the option to follow logs. |
| `status` | Show services, health and ports. |
| `url` | Print the playground URL. Boxie mode prints the API URL. |
| `down` | Remove the selected worktree's projects and disposable data. Images can be reused. |
| `config` | Print Compose configuration with placeholder credentials. A running engine is optional. |
| `doctor` | Check Docker, show its context and version, and validate configuration. |

Use `logs --mode boxie` to follow Boxie from a full deployment. If startup
fails, inspect `status` and `logs` in the selected mode. Rebuild with `start`
after changing source. A recreated container can receive a new loopback port,
which `url` reports.

## Multiple worktrees

Project names incorporate the canonical checkout path. A second worktree has
its own playground database, volumes and ports, even when both playgrounds use
the same external Boxie. Tear down a worktree before moving or deleting it so
the launcher can identify its resources. Keep the Boxie files under
`.local-dev/boxie/` while the project is running. To reset that development
installation, use `down --mode boxie` or `down --mode full` before starting again.

Use a local Docker context because the printed loopback URLs refer to the
Docker host. To manage a specific checkout from elsewhere, use the installed
launcher.

```sh
sdev --root /path/to/another/worktree local status --mode full
```

For production-style operator setup, see the [Boxie deployment guide](../packages/boxie/docs/deployment.md)
and [playground deployment guide](../tools/cli-playground/docs/deployment.md).
For a reviewable CLI demo, follow the [CLI recording guide](cli-development.md#record-a-visible-change).

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
