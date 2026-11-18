# local-dev

Start a playground and PostgreSQL for the current Sanctuary checkout. From the
repository root with Docker Compose running, build the images and open the URL
printed when the services are ready.

```sh
uv run --locked local-dev start
```

`local-dev status` reports the worktree's services. `local-dev down` removes its
containers and disposable data. Install the standalone command with
`uv tool install ./tools/local-dev` from the repository root, or use `sdev
local` with the same flags. See the [local development guide](../../docs/local-development.md).
