# Playground previews

Open **Sanctuary / Playground** on a PR commit to use its deployed CLIs. Open, ready, same-repository PRs qualify when their complete merge-base diff touches a CLI or shared CLI inputs. Production and previews share Boxie. Each preview gets a distinct hostname, database and consumer key. [Preview release and removal](../../../infra/docs/releases.md#pr-previews)

## Build and comparison contract

The builder exports metadata from the exact copied head executables, resolves `git merge-base`
for the supplied base and head commits, and builds corresponding baseline CLIs in
an isolated source directory. Export invokes each binary with exactly `--help`
and `SANCTUARY_CLI_SCHEMA=1`, before its normal parsing or logging. Each capture
has a ten-second deadline and a 1 MiB output limit. Its working directory is
empty and its environment excludes ambient credentials. Execution occurs only
inside the disposable build container.

The baseline build has a ten-minute deadline. A missing exporter, failed baseline
build, or invalid baseline export yields an unavailable comparison. A CLI absent
from the merge base is added. A failed head export fails the catalog-producing
build, rather than publishing an incomplete reference. `true` and `false` export
explicit empty interfaces while retaining their normal exit behavior.

The flat binary ZIP may include one `catalog.json` sidecar, at most 4 MiB including
its canonical representation. Its version 1 envelope records `head_sha`,
`base_sha`, and one entry per published executable with its name, SHA-256 digest,
head command tree, optional baseline tree, and comparison availability. The
[shared exporter](../../../utils/cli-schema/README.md) defines the tree fields.
The [catalog validator](../src/cli_playground/catalog.py) owns structural limits:
up to 1,024 CLIs, depth 16, 4,096 command nodes and 32,768 arguments across both
trees, with bounded strings and collections. Unknown versions and fields,
duplicate identities, invalid names, and unsafe control characters are rejected.

The publisher verifies the bundle checksum. Gateway admission validates the sidecar against the
expected head SHA and the exact executable names and digests. They never execute
uploaded binaries. These checks bind descriptions to an artifact; they cannot
prove that untrusted PR code describes itself honestly. The recorded merge-base
SHA is a comparison identity, not independent evidence of behavior.

The gateway strips the sidecar from the executable ZIP sent to Boxie and stores
its canonical digest and contents with the upload intent and immutable revision.
A retry with different metadata conflicts even when the binaries are unchanged.
[Recovery](database.md) preserves the same catalog through interrupted publication.

### Retrieve a revision's catalog

`GET /api/environments/{id}/revisions/{revision}/catalog` returns the versioned
catalog with status 200, or JSON `null` for a legacy binary-only revision. It is
public under the same preview-link access model as build metadata. Unknown,
expired, or closed previews and unavailable revisions return 404. Revision IDs
are the SHA, or `SHA-run_number-run_attempt` for workflow builds.

Catalog retrieval is separate from build-status polling. The browser fetches it
when it opens or explicitly switches builds, and on **Retry**. Matching uses
argument IDs within a command path, then unambiguous public spellings. Command
renames can match through public aliases; ambiguous renames become additions and
removals. Ordering and whitespace-only prose changes are ignored, as is generated
usage layout. Explicit usage overrides, short/full help, flags, operands, defaults,
choices, requiredness, value counts, and global ownership are represented.
