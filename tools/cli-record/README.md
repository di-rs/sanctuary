# cli-record

Record the named CLI demos you want to show in a pull request. From a Sanctuary
checkout, list a package’s demos and choose one to film.

```sh
uv run --locked cli-record echor --list
uv run --locked cli-record echor no-newline
```

Demo names and inputs come from the package’s `tests/browser.toml`. Recording
builds the selected binary in a disposable local playground and films the real
terminal in Chromium. The command prints the WebM directory when it finishes.
Pass multiple names in display order or use `--output DIR` for a new output
directory.

Use `sdev record` with the same arguments. For a standalone installation, run
the following from the repository root.

```sh
uv tool install --with ./tools/cli-check --with ./tools/local-dev ./tools/cli-record
```

See the [CLI development guide](../../docs/cli-development.md#record-a-visible-change)
for browser setup, demo fields and PR attachment instructions.
