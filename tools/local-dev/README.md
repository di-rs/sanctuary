# sanctuary-dev

Check a Sanctuary CLI from your checkout. For example, run the package policy,
formatting, lint and native tests for echor.

```sh
uv run --locked sanctuary-dev check echor
```

After `uv sync --locked --all-packages`, activate the environment with
`. .venv/bin/activate` to use `sanctuary-dev` directly. Use `sanctuary-dev
record echor --list` to find a named demo or `sanctuary-dev up` to start
the worktree's playground. Existing scripts can also use the `local-dev` name.

See the [CLI development guide](../../docs/cli-development.md) for recording
and attaching a change to a PR, and the [local development guide](../../docs/local-development.md)
for Docker setup, console output and shutdown.
