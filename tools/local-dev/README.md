# local-dev

Run the CLI playground or Boxie for a Sanctuary worktree. From the checkout
root with Docker Compose running:

```sh
uv run --locked local-dev start
```

The default playground uses portable Bash PTYs. Use `--mode boxie` for
standalone Boxie on Linux with gVisor, `--mode full` to run both projects, or
`--mode external` to connect the playground to a development Boxie.

Run `status` or `down` with the same mode to inspect or remove the selected
worktree's resources. Install the standalone command with
`uv tool install ./tools/local-dev` from the checkout root, or use `sdev local`
with the same arguments. [Local development guide](../../docs/local-development.md)
