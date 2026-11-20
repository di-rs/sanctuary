# Recall the build command for a release checkout in Shish

A documentation maintainer builds the latest manual with `make site` and
the release manual with `make html`. Opening a new terminal for a release
correction, they remember typing `make`. Shish could use that prefix to
recall the most recent command that exited zero in the current directory
and put it at the prompt for editing.

Shish's Bash mode already saves command text. Atuin gives Bash and Zsh
users a local SQLite history that also records working directories and
exit codes. A user who searched Atuin from a linked Git worktree reported
seeing only commands from the main checkout. Atuin documents that its
workspace filter searches under the main repository root.
[Atuin's local history](https://docs.atuin.sh/18.24/),
[worktree report](https://github.com/atuinsh/atuin/issues/3819) and
[workspace filter](https://docs.atuin.sh/18.24/configuration/config/#workspaces)

## Which build would the shortcut recall?

An offline trial used Atuin 18.24.8 and two sibling Git worktrees. In
the release checkout, `make pdf` and `make html` succeeded, then
`make site` exited 2. The same `make site` command succeeded in the
main checkout. A test driver passed each exit status from Shish to
Atuin. When it withheld the status for a final `make proof` in the
release checkout, Atuin listed that entry with exit `-1`.

| Search from a new terminal at the release root | Most recent match |
| --- | --- |
| All directories, exit 0 | `make site` |
| Git workspace, exit 0 | `make site` |
| Current directory, any status | `make proof` |
| Current directory, exit 0 | `make html` |

With those entries in Atuin, run this query from the release root.
[Atuin search options](https://docs.atuin.sh/18.24/reference/search/)

```sh
atuin search --filter-mode directory --exit 0 --limit 1 \
  --search-mode prefix --cmd-only -- make
```

In an interactive `shish --bash` terminal on macOS, pressing Ctrl-G
with a test binding inserted `make html`. Adding `-n` and pressing
Enter printed the recipe. Accepting the original line afterward ran
the recipe once. A separate test shows why the shortcut should say
**Shell exit 0**. The line `make site | cat` qualified even though
`make` reported a missing target.

## Record commands in a local Shish session

Shish skips shell startup files, so the trial loaded the binding with
the shell's `.` command. For automatic recording, let maintainers opt
in from an interactive `shish --bash` session. Give each terminal an
Atuin session ID. Call `atuin history start` from the line's starting
directory with the original text as one argument. If Atuin returns a
command ID, pass it and the shell's observed exit status to
`atuin history end` when the line finishes.
[Shish startup](../../packages/shish/README.md#startup-and-configuration)
and [Atuin's shell hooks](https://docs.atuin.sh/18.24/guide/shell-integration/)

Use a fresh local Atuin store with sync disabled for the trial. Atuin
skipped a sample command entered with a leading space. Shish still wrote
it to its own plaintext history file on exit. For a session using Atuin
as its only disk history, `unset HISTFILE` inside Shish disabled the
automatic save for all commands in that session.
[Atuin history exclusions](https://docs.atuin.sh/18.24/guide/excluding-commands/)
and [Shish history](../../packages/shish/README.md#interactive-history)

## Would maintainers use it for their next release?

Ask four maintainers who work in parallel release checkouts to find and
dry-run the right target for two manuals. Record the same attempts in
both tools, including a failed release build and a later successful main
build. Use the shortcut for one manual and each maintainer's usual history
search for the other, including Atuin where they already use it. Swap
the assignments for half the group.

Time each lookup from opening a fresh terminal to previewing the correct
recipe. Add automatic recording to Shish if all four select the right
target with the shortcut and at least three save 30 seconds over their
usual search and ask to try it on a release of their own.
