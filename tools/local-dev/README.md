# local-dev

Run the Sanctuary playground, all workspace CLIs, and PostgreSQL in a separate
Docker Compose project for each worktree:

```sh
uv run local-dev up
```

Run from a Sanctuary checkout with uv and a running local Docker engine with
Compose installed. The command builds images, waits for health, prints the
assigned loopback URL, and follows logs. Ctrl+C leaves services running.
Use `uv run local-dev down` to remove this worktree's stack and disposable data.

See the [local development guide](../../docs/local-development.md) for all commands,
worktree isolation, rebuilding, troubleshooting, and the development transport's
limits. `uv run local-dev --help` lists commands without contacting Docker.
