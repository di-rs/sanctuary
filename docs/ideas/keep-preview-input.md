# Keep a test file when switching CLI builds

A reviewer trims a failing input down to three lines in Sanctuary's browser
terminal. The author pushes a fix. **Switch to latest build** opens a fresh
workspace, so the reviewer has to recreate the file to try the fix. A proposed
**Keep case.txt and switch** action would carry that one file into the new
build and show which revision received it.
[Playground build switching](../../tools/cli-playground/docs/architecture.md#command-explorer-and-terminal-ownership)

A Binder user asked how to pick up a repository update in a running session.
A maintainer said the choice between restarting and merging depended on how
much the user had edited. Binder also lets users save an edited notebook in
the browser and restore it into a new session. Google Cloud Shell offers a
manual option for shell users who want to download a file to their computer
and upload it again.
[Binder user's question](https://discourse.jupyter.org/t/updating-binder-from-changes-on-github/7731),
[Binder notebook recovery](https://discourse.jupyter.org/t/getting-your-notebook-after-your-binder-has-stopped/3268)
and [Cloud Shell file transfers](https://docs.cloud.google.com/shell/docs/uploading-and-downloading-files)

## When copying three lines changes the result

Try this in a fresh playground terminal for a build that includes `uniqr`.

```sh
printf 'ok\r\nok\nok\r\n' > case.txt
uniqr -c case.txt
```

All three lines say `ok`. The first and third end in a carriage return and a
line feed (CRLF). The middle one ends in a line feed alone. `uniqr` keeps the
carriage return when comparing adjacent lines. The playground's terminal
renderer, xterm, displayed both 11-byte files identically in Chrome. The
counts below come from running the same macOS build of `uniqr` on each
file and on the text selected from the screen.
[How uniqr compares lines](../../buildins/uniqr/README.md#before-using-it)

| Input | Bytes | Consecutive run counts |
| --- | ---: | --- |
| Original file | 11 | 1, 1, 1 |
| Same text with CRLF on the first and second lines | 11 | 2, 1 |
| Text selected from the three visible lines in the terminal | 8 | 3 |

To carry the file manually, run `base64 case.txt` in the original terminal.
It prints `b2sNCm9rCm9rDQo=`. Copy the encoded text before switching, then
decode it in the new workspace to reproduce the original counts.

```sh
printf '%s' 'b2sNCm9rCm9rDQo=' | base64 -d > case.txt
uniqr -c case.txt
```

## Carry the bytes through the switch

The reviewer would finish editing `/workspace/case.txt` and select the new
build. Before switching, the page would hold the complete file in memory as
a browser `Blob` and check its SHA-256 digest against the source. A missing
file, a digest mismatch or a file over the pilot's 64 KiB limit would leave
the reviewer on the current build. If a newer build supersedes the selected
one before the next session opens, the tab would hold the file until the
reviewer accepts the new revision. Closing or reloading the tab would
discard its copy.

Boxie, Sanctuary's private sandbox runtime, gives each terminal a temporary
filesystem. The pilot would need a private file transfer in Boxie, scoped to
the consumer's live sandbox. The playground gateway would check the browser
session's credential and revision on each transfer. A helper running as the
sandbox user would read only a regular file at the fixed path, refusing
symbolic links. In the new workspace it would stage the bytes, verify the
original digest and put `case.txt` in place only if the name is free.
[Boxie sandbox API](../../packages/boxie/docs/consumer-api.md#manage-artifacts-and-sandboxes)
and [workspace lifetime](../../packages/boxie/docs/execution.md#isolation-and-lifetime)

In a Chrome prototype, a test adapter transferred the file between Docker
Desktop containers. After removal of the source container, a restore missing
its last byte left no `case.txt` in the new workspace. Retrying from the same
tab recovered all 11 bytes and the original counts. An attempt to restore
different bytes over the existing file left its contents intact.

## Would reviewers use it on their next fix?

Have four CLI reviewers each bring a small input they edited during a review.
On a private Linux host with gVisor, alternate the proposed switch and each
reviewer's usual method across comparable fixes. Give everyone the Base64
recipe. Time from the build notification to the first correct rerun,
including any renaming of the input. Check the build revision and file
digest on every run. Interrupt one restore for each reviewer. Keep the
feature if all four use the intended file and build with Sanctuary, all four
recover from the interruption, and at least three save 30 seconds per switch.
