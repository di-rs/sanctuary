# Find the right manual for a CLI support ticket

After a forward search in Kara 0.2.0, one build advances with lowercase
`n` and another with uppercase `N`. A support engineer who tries the
keys on their own copy of Sanctuary's terminal editor can give a tester
the wrong answer. A proposed **Ask about this build** action would open
the manual for the executable in the ticket and let the engineer check a
local model's answer against the cited passage.

## Which key moves to the next match?

Two local builds of Kara printed the same help text and exported the same
command schema. An automated terminal test started each search on the
middle occurrence in `hit--hit--hit`, pressed `n` or `N`, and inserted
an `X`. The saved file showed where the cursor landed.

With network access disabled, a local six-bit Qwen3.8-27B model received
the numbered **Search** section from one build's README at a time. After
each kind of search, which key would move toward the end of the file?
[Model used in the trial](https://huggingface.co/lmstudio-community/Qwen3.8-27B-MLX-6bit)

| Kara source commit | Accepted search | Key that reached the third match | Model's answer and cited line |
| --- | --- | --- | --- |
| `8ac240b4` | `/hit` (forward) | `n` | `n`, line 60 |
| `8ac240b4` | `?hit` (backward) | `N` | `n`, line 60 |
| `01c4db43` | `/hit` (forward) | `N` | `N`, line 61 |
| `01c4db43` | `?hit` (backward) | `N` | `N`, line 61 |

Line 60 in the older manual says that lowercase `n` repeats the accepted
direction. After a backward search that key moved to the first match.
The model cited the right line and interpreted it incorrectly. Given
both manuals together and only the version number, it picked uppercase
`N` for the forward search, which works on just the newer build.

From a Sanctuary clone containing both commits, an engineer can read the
two passages without switching branches.

```sh
git grep -n -A12 -F -e '## Search' 8ac240b4 01c4db43 -- packages/kara/README.md
```

## How the engineer would select a manual

An engineer can already export a README from Git, attach it as a text
file in LM Studio, and ask questions offline with a downloaded model.
Teams that maintain a larger collection can index local folders in
Grounded Docs and search each library version without an embedding model.
Either workflow starts with someone matching the ticket to a manual.
[LM Studio offline document chat](https://lmstudio.ai/docs/app/offline)
and [Grounded Docs search](https://github.com/arabold/docs-mcp-server#features)

Context7's hosted search accepts a requested version and flags when it
serves a different one. Even an exact release number would leave the
two Kara builds tied. [Context7 version selection](https://context7.com/docs/api-reference/search/search-documentation-in-one-request)

Use records from the team's build system. Sanctuary's optional playground
catalog already pairs the source commit with the executable's SHA-256
digest. Its validator accepted a locally prepared catalog for each Kara
build and rejected one paired with the other executable. The engineer
would select the ticket's build record or look up the executable by
digest. If the match is ambiguous, **Choose a build** would ask for the
build ID before drafting a reply.
[Playground build catalog](../../tools/cli-playground/docs/previews.md#build-and-comparison-contract)

The engineer could read a section of the committed README or send it with
a question to LM Studio on loopback. For the newer build, the viewer could
show **Press uppercase `N`** beside line 61 of `packages/kara/README.md`
at `01c4db43`. Opening the citation would read that commit even after a
branch switch. Choosing another build would start a fresh conversation.
If the commit or README is missing locally, **Manual unavailable** would
name the revision to obtain.
[LM Studio local server](https://lmstudio.ai/docs/developer/core/server)

## Decide whether to add it to support tools

Ask two teams maintaining private CLI builds for six past support tickets
each. Include two builds sharing a version, a ticket with only that
ambiguous version, and one whose manual is absent from the local clone.
Give two engineers on each team the same build records. Let each try half
the tickets with automatic manual selection and half with Git search and
manual attachment to the same local model. Swap assignments so each
ticket is tried both ways by different people.

Check each reply against the behavior of the reported build. For the two
cases with missing information, score whether the engineer identifies
what they need to answer. Try a support integration if both teams resolve
those cases correctly, produce at least as many correct replies, and cut
median time to a correct reply by at least 20%. Include time spent matching
builds and checking citations on both paths.
