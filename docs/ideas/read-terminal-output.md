# Find an earlier terminal error with a screen reader

A pull request reviewer needs to quote the filename from an error in
Sanctuary's browser playground. By the time they reach the prompt, sixty
more lines have scrolled past. A proposed **Read terminal output** button
would let them search the text still in the tab, copy the diagnostic into
their review and return to the same shell.

In two studies with 12 developers who use screen readers, participants
described reading long command output in a text file where they could
navigate it more easily. Google Cloud Shell offers a shortcut to hear the
current row. VS Code's Accessible View lets a developer inspect terminal
output line by line or character by character.
[CLI accessibility study](https://storage.googleapis.com/gweb-research2023-media/pubtools/6065.pdf),
[Google Cloud Shell keyboard controls](https://docs.cloud.google.com/shell/docs/using-cloud-shell-accessibility-features)
and [VS Code terminal accessibility](https://code.visualstudio.com/docs/configure/accessibility/accessibility#_terminal-accessibility)

## What the reading view would show

The playground already enables xterm's screen-reader mode and keeps up to
5,000 rows of scrollback above the screen. A toolbar button and a shortcut
from inside the terminal would open a read-only dialog in the Svelte
frontend. It would copy the normal shell screen and its scrollback as
plain text. The copy would stay in page memory until the reviewer closes
the dialog, resets the session or switches builds.
[Playground terminal settings](../../tools/cli-playground/frontend/src/terminal/browser.ts)
and [terminal recovery](../../tools/cli-playground/README.md#terminal-recovery)

The text would reflect what the terminal retained. A progress indicator
that rewrites one line contributes its last displayed value. The action
would become available again when a full-screen editor returns to the
shell.

## One missing file followed by 60 records

In a fresh Bash playground with `catr` on `PATH`, these commands produce
one file-open error followed by 60 records. `catr` processes the readable
file and exits with status 1. [How catr handles missing files](../../buildins/catr/README.md#before-using-it)

```bash
printf 'accepted batch %02d\n' {1..60} > accepted.log
catr april-manifest.tsv accepted.log
```

A standalone Chrome page received the command's terminal output using the
playground's pinned xterm.js 6.0.0. At 24 columns and six rows, the final
screen showed batches 56 through 60 and an empty row. The error occupied
four earlier rows. The first ended with `april-man` and the next began
with `ifest.tsv`. Joining the rows xterm marked as wrapped let Chrome
select the whole filename in the dialog. Its accessibility tree contained
the complete diagnostic.
[xterm's buffer line API](https://xtermjs.org/docs/api/terminal/interfaces/ibufferline/)

New terminal output and a resize left the filename selected. Escape
returned focus to xterm. Opening, navigating and closing the dialog sent
zero characters to the terminal. After 5,010 more lines, a fresh snapshot
started past the error.

## Try it with four reviewers

Invite two developers who use NVDA with Firefox and two who use VoiceOver
with Safari. Give each person two previews, each with a different missing
file among several inputs and the same volume of later output. Use today's
terminal for one and the reading view for the other. Swap the order and
the examples within each pair. Ask each reviewer to copy the exact
diagnostic while more output arrives, then return to a half-typed command
and finish it.

Allow two minutes per preview. Adopt the view if all four complete the
task unaided with their command intact and at least three finish faster
than with today's terminal. A baseline timeout counts as the full two
minutes. Record any point where new output interrupts speech or moves
the reviewer's reading position.
