# Watch a teammate's running preview terminal

A release engineer expects a space in the French manual's filename.
The package uses a hyphen. They ask a maintainer to look while they try
a correction.
Opening the pull request's playground link gives the maintainer a fresh
workspace in Boxie, Sanctuary's sandbox runtime.
A proposed **Invite a viewer** action would let the maintainer copy the
missing path from the engineer's terminal, watch the next comparison and
cite the build they both saw. [How playground previews work](../../tools/cli-playground/README.md#use-a-preview)

VS Code Live Share lets a host start a read-only shared terminal. A team
already streaming to its own asciinema server can send its viewer link.
The server tracks the screen so someone joining halfway through can see
what is on display. Sanctuary could bring that experience to a session
the engineer started as an ordinary pull request preview.
[Live Share terminal permissions](https://learn.microsoft.com/en-us/visualstudio/liveshare/use/share-server-visual-studio-code#share-a-terminal),
[asciinema streaming options](https://docs.asciinema.org/getting-started/#live-streaming)
and [how asciinema handles late viewers](https://docs.asciinema.org/manual/server/streaming/#architecture)

## What a late viewer needs

In a scratch directory with `commr` on `PATH`, compare the expected
and packaged filenames. The space in the result matters to the reviewer.
[Comparing two sorted files](../../buildins/commr/README.md#arguments-and-options)

```bash
printf '%s\n' 'manuals/en.txt' 'manuals/fr CA.txt' > expected
printf '%s\n' 'manuals/en.txt' 'manuals/fr-CA.txt' > packed
commr -2 -3 expected packed
```

In a local trial, the command printed `manuals/fr CA.txt`. A synthetic
progress counter then rewrote the line below it 4,100 times. Feeding each
redraw to Boxie's replay buffer as one frame used up its 4,096-frame
capacity with just 52 KiB retained. A request to replay from the beginning
returned `stream_gap`. A fresh terminal given the retained bytes displayed
only `checked 4100`.
[Boxie terminal replay limits](../../packages/boxie/docs/consumer-api.md#control-and-output-frames)

The filename was still visible on a 13-column screen in xterm.js 6.0.0,
wrapped across two rows. A prototype joined the wrapped rows and
sent the current screen as text through a loopback relay. A second Chrome
session selected the full path and received the next update, `checked 4101`.
Typing in the viewer and resizing its window sent zero characters to the
author's terminal and left it at 13 columns.

## Sharing one screen on a private deployment

Try this behind the team's existing sign-in. The engineer would preview
the text a colleague could copy, including echoed commands, then choose
whom to invite. The playground gateway would grant that account access
to the text feed for this session and display the revision from the
session record.

Boxie gives control to the newest terminal attachment. The engineer's
tab would keep that connection and publish screen updates to the
gateway. The viewer would receive the text through server-sent events.
[Boxie attachment ordering](../../packages/boxie/docs/consumer-api.md#order-attachment-attempts)

The gateway would hold one size-limited screen per share in memory and
cap how often it sent updates. A slow viewer could pick up at the latest
screen. **Stop sharing**, a sandbox reset, a build switch or loss of
contact with the engineer's tab would close the feed, expire the link
and discard the gateway's copy.

The prototype paused when the engineer scrolled into history, when xterm
switched to its alternate screen or when a cell was marked invisible.
Reading an xterm row as text included a concealed test word.
Checking the cells before publishing kept that word out of the feed.
[xterm buffer cell attributes](https://xtermjs.org/docs/api/terminal/interfaces/ibuffercell/#isinvisible)

## Try it during four paired reviews

Recruit four pairs who recently asked a teammate to reproduce something
they could already see in a preview. Give each pair two similar manifest
errors. Use the viewer for one and the pair's quickest usual method for
the other, including pasting into chat or sharing a tab. Vary which
method goes first and which error each method gets. Start the clock when
the engineer asks for a second look. Stop when the maintainer reports the
exact path, build revision and result of the correction.

Try a wider rollout if all four pairs report all three facts correctly
with the viewer and at least three save a minute against their usual
method. On the private deployment, verify that only the invited account
can watch and that ending a share closes the active viewer and prevents
reconnection.
