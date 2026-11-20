# CLI playground

Try a pull request's Rust commands in a browser terminal. Each PR gets a stable
preview URL, and each browser tab gets Bash, sample files, and a disposable
workspace. All included CLIs share `PATH`, so you can try pipelines.

## Use a preview

Open the PR's playground link. The command builder follows the current Bash
input: an empty prompt shows CLI buttons; typing `biggie` shows its commands;
`biggie t` narrows those commands and highlights the matching text. Choose `text`
to complete the draft to `biggie text` and see its flags. Unknown commands show
**No command found**. There is no separate CLI selection or search state.

Clicks replace the editable draft rather than appending another executable.
Commands use their plain names on `PATH`. Clicking a flag adds its spelling;
flags that take values prompt you to type one or choose an exported enum value.
Nothing presses Enter or inserts placeholder operands. **All CLIs** clears the
draft so you can start another command. Sample files and shell essentials remain
below the builder. On narrow screens, **Explore** opens a drawer.

Added and changed flags carry inline badges. Comparisons use the PR's recorded
merge base and describe declared interfaces, not runtime behavior or custom
validation absent from parser metadata. Missing baselines receive no speculative
badges. Older binary-only previews show **Command reference unavailable**.

Suggestions cover one simple command. Pipes, redirects, shell expansions, and
unfinished quotes remain available in Bash but have no suggestions. Builder
editing requires the sandbox's Bash prompt integration and is disabled while a
program runs. Deploy the updated sandbox image before using this frontend;
existing shells without prompt markers remain usable as terminals.

Typing, suggestions, and drawer changes preserve the terminal connection and
files. The catalog stays pinned to its build. **Switch to latest build** and
**Reset session** end the old session and start a fresh workspace.

A connection drop can resume the same terminal on the current page. Reloading the
page starts fresh. Sessions expire after 60 minutes, ten idle minutes, or two
minutes disconnected, whichever limit applies first. Sandboxes have no network.

## How a preview reaches the browser

The protected publisher selects open, ready PRs with CLI changes, builds their executables inside a disposable container and stages each bundle in private R2. The host deploys the PR gateway against the shared Boxie instance. Open the **Sanctuary / Playground** commit status to visit that revision. Boxie starts a sandbox when a visitor opens a terminal. [Preview operations](../../infra/docs/releases.md#pr-previews)

## Run locally

From the repository root, with uv installed and Docker and its Compose plugin running:

```sh
uv run --locked sdev local up
```

The launcher builds the frontend and all CLIs, starts the disposable Compose
playground, waits for health checks, and follows logs. Open
the assigned loopback URL when it prints `Ready`. Ctrl+C leaves services running;
`uv run --locked sdev local down` stops and removes them.

The [local development guide](../../docs/local-development.md) explains prerequisites,
components, exact Compose commands, rebuilding, logs, cleanup, and troubleshooting.
The portable setup uses real Bash and PostgreSQL with a development Boxie transport;
it does not exercise production Temporal or gVisor isolation.

### Run against a real Boxie service

The UI uses Svelte and TypeScript; the server uses Python/FastAPI. Before starting
the backend, provision a private [Boxie service](../../packages/boxie/docs/deployment.md)
and a separate PostgreSQL database. [Playground infrastructure](docs/deployment.md)
covers Compose and production deployment.

Interactive sandboxes require native Linux with gVisor. Docker Desktop can build
images and run the UI against a separately operated Boxie service, but cannot
provide the required sandbox runtime.

### Build the frontend

Run from the repository root:

```sh
uv sync --all-packages
pnpm --dir tools/cli-playground/frontend install
pnpm --dir tools/cli-playground/frontend build
```

The build writes assets to `src/cli_playground/static/` within this package.
Those assets are included in the Python wheel and sdist.

### Configure the backend

Set these values before starting the service:

| Variable | Purpose |
| --- | --- |
| `CLI_PLAYGROUND_DATA_DIR` | Storage for pending upload ZIPs |
| `CLI_PLAYGROUND_PUBLIC_URL` | Public playground URL |
| `CLI_PLAYGROUND_DEPLOY_TOKEN` | Credential for publishing previews |
| `CLI_PLAYGROUND_BOXIE_URL` | Private Boxie API URL |
| `CLI_PLAYGROUND_BOXIE_CREDENTIAL_FILE` | Consumer secret in a private regular file, mode `0600` |
| `CLI_PLAYGROUND_DATABASE_URL` | PostgreSQL connection URL, using `postgresql+psycopg://USER:PASSWORD@HOST/DATABASE` |

The database URL can instead be stored in
`/run/secrets/CLI_PLAYGROUND_DATABASE_URL`. Environment values take precedence.
Use a database login separate from Boxie's.

### Migrate and start

Apply the schema before starting the gateway:

```sh
uv run --package cli-playground alembic \
  -c tools/cli-playground/alembic.ini upgrade head
uv run --package cli-playground uvicorn cli_playground.app:create_app \
  --factory --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

Keep one worker. Upload serialization and startup recovery assume a single
gateway; PostgreSQL alone does not make multiple replicas safe.

The playground talks to Boxie through its API. Its image contains no Docker
client, Docker socket, or Boxie implementation, and the consumer secret stays
on the server.

## Terminal recovery

The browser keeps terminal credentials, the last applied output sequence, and
screen contents in page memory. On reconnect, it drains pending xterm writes,
replays retained output exactly once, and synchronizes terminal dimensions before
enabling input. Input typed while disconnected is discarded.

The server allocates Boxie's increasing attachment order from its persisted page
claim. Browser frames cannot select or override that order.

An expired session or a gap in retained output offers a fresh sandbox. There is
no persisted cursor or screen snapshot to restore after a page reload.

## Develop the service

### Change terminal input handling

The `terminal/input-intent.ts` adapter uses xterm's internal `triggerDataEvent`
source flag to distinguish user input from terminal-generated
replies. Those replies must keep working during replay without renewing idle time.
The xterm dependency is pinned in [package.json](frontend/package.json). The
adapter checks the version and runtime shape and fails on unsupported bundles.

The sandbox marks prompt boundaries with OSC 133. The browser reads the echoed
input from xterm's normal buffer after writes, so history and Readline edits
update the builder. An explicit builder click sends a fixed Readline clear-line
binding, then pastes the new draft with no Enter. Prompt markers are UI hints,
not authentication; sandbox output remains untrusted. Draft text stays in page
memory and is not sent to a search service or telemetry.

When upgrading xterm, run the browser suite for keyboard input, paste, asynchronous
composition, and parser replies. Its DOM composition tests do not cover OS-native
input method editors (IMEs).

### Change storage or diagnose failures

Read [persistence](docs/database.md) before changing session recovery or
metadata storage, and [request tracing](docs/observability.md) to diagnose an action
across services. The [PR workflow](../../.github/workflows/pull-request-check.yml)
checks Python, frontend, and browser behavior; the
[native lifecycle workflow](../../.github/workflows/sanctuary-lifecycle.yml)
checks the Linux/gVisor deployment.

## Documentation

- [Architecture](docs/architecture.md)
- [Database](docs/database.md)
- [Observability](docs/observability.md)
- [Deployment](docs/deployment.md)
- [Previews](docs/previews.md)

[Repository architecture](../../docs/architecture.md)
