# Cleanup plan for the durable shell platform

Fix two confirmed cases of local data loss first. Then bring Boxie's default
sandbox back onto a supported base, prove its packaging works independently of
the playground, and consolidate the duplicated GitHub publishing code. The next
consumer-facing capability is cancellation of an accepted job.

Boxie owns admission, isolation and recovery. Shish runs locally through Brush.
The playground owns previews and browser sessions. Keep those boundaries while
working through the queue. Account self-service, custom templates, automatic job
retries and shell checkpoints need a separate consumer requirement and recovery
contract. [Platform direction](platform-direction.md) · [Current architecture](architecture.md)

The CLI applications already work together through files, pipes and terminals.
Shish ran Biggie records through the builtins and piped JSON from echor to Parsu.
Kara edited and saved a file through its terminal interface. For a browser
preview, the build exports executables and can include a command catalog. The
playground validates both, stores the catalog and sends only the executable
bundle to Boxie. Boxie runs the executables in its fixed Bash environment.
The ten shared terminal message schemas agreed. On attachment the gateway also
supplies the ordering field that Boxie enforces.

## Order of work

Take one row at a time. P0 means immediate work to prevent demonstrated data
loss. P1 covers the next cleanup or a release or operations gate. P2 follows
baseline cleanup. P3 needs an identified user and capacity for optional work.
Complete the notices work before distributing an affected artifact and the
restore drill before relying on production state. Development and local
verification can proceed independently of both gates. The [component
follow-ups](#follow-up-cleanup) identify checks to complete when their owners
change a specific workflow.

**P1 before the next merge. Reconcile the default branch's required checks.**
The checked-in ruleset lists four GitHub Actions checks. On November 18 the
effective rule required only `Production persistence risk assessment`, although
`Sanctuary validation`, `git-policy` and `Local CLI recordings` also ran and
passed on PR #320. The checked-in rule selects squash merges, and GitHub also
permits merge commits. Repository maintainers should reconcile the live rule
with the intended policy, confirm each required context and app ID on a real PR,
and compare the effective rule with the checked-in copy on a schedule.
[Checked-in ruleset](../.github/rulesets/gitmoji-commits.json) ·
[Effective ruleset](https://github.com/di-rs/sanctuary/rules/25029558)

| Order | Priority | Work and timing | Evidence to finish |
| --- | --- | --- | --- |
| 1 | P0 | Fix `uniqr` before its next distribution. A 14-byte file passed as both redirected stdin and named output was truncated to zero with exit 0. [#318](https://github.com/di-rs/sanctuary/issues/318) | Compare the open input and output before truncation. The same path, a hard link and a symlink each return 65 and preserve the input. Pipes and distinct destinations still work. |
| 2 | P0 | Fix Kara's save behavior before its next distribution. Ctrl-S on a clean buffer replaced text saved by a second writer. [#319](https://github.com/di-rs/sanctuary/issues/319) | A clean save preserves the external change. A dirty buffer detects a change completed before save, retains edits and allows Save As. Cover both writers through the terminal. |
| 3 | P1 | Finish the fixed Boxie environment before the next sandbox publish or rollout. Interactive creation already accepts an artifact ID, and the naming cutover is complete. [#70](https://github.com/di-rs/sanctuary/issues/70) · [Original implementation](https://github.com/di-rs/sanctuary/pull/74) · [Cutover cleanup](https://github.com/di-rs/sanctuary/pull/76) | Restore the supported base in both Dockerfiles. Move consumer packaging and shared-host assertions to their owners. Prove Boxie works with consumer sources absent. On changes to the shipped sandbox image or startup files, build that image on the PR and run a native command under gVisor. The full shared suite covers upload, attach, reconnect and cleanup. |
| 4 | P1 | Consolidate GitHub publication code before adding another publisher. [Open simplification task](#simplification-task) | One bounded GitHubKit transport and one contract suite serve preview, benchmark and binary-size reporting through their existing entry points. |
| 5 | P1 | Package notices before the next affected binary or image distribution. Image publication can precede deployment. [#201](https://github.com/di-rs/sanctuary/issues/201) | Generate notices from what ships for each target. Reuse the frontend's generated notices and inspect final images and archives. Preserve the executable-only preview format and its catalog sidecar. |
| 6 | P1 | Prove off-host recovery before relying on retained production state. [#38](https://github.com/di-rs/sanctuary/issues/38) | Restore the three Boxie/Temporal databases, artifacts and required identity material onto a fresh host. Fence the former owner and reconcile jobs whose effects may postdate the backup. Record the recovery point, elapsed time, alert test and a successful new job. |
| 7 | P2 | Decide who dispatches accepted work before changing API access to Temporal. [#72](https://github.com/di-rs/sanctuary/issues/72) | Compare the API's post-commit delivery attempt with the supervisor loop. Measure dispatch and stop latency. Document readiness, credentials and recovery under duplicate delivery, restart and outages. |
| 8 | P2 | Decide where admission rules and transactions belong. Share the failure cases with #72. [#73](https://github.com/di-rs/sanctuary/issues/73) | Trace a terminal and a job through existing application ports. Produce a decision that keeps idempotency, capacity, artifact and output reservations, and the outbox atomic. Cover concurrent retries and rollback. |
| 9 | P2 | Add consumer cancellation before onboarding a job client that needs it. Job submission, inspection, bounded results and same-host single-attempt recovery shipped in [PR #307](https://github.com/di-rs/sanctuary/pull/307). [#37](https://github.com/di-rs/sanctuary/issues/37) | Reuse the stop transaction and start fence. Exercise repeat and foreign requests, completion races, restart and cleanup. Preserve recorded results and ambiguous outcomes. This can ship on the existing architecture. |
| 10 | P3 | Revisit the Ask Codebase CLI when a maintainer can identify a recurring question existing tools handle poorly. [#94](https://github.com/di-rs/sanctuary/issues/94) | Compare existing tools on real questions. If a gap remains, test a read-only one-shot prototype with source citations and cancellation before committing to the TUI. |

The sandbox image and its integration fixture select Ubuntu 25.10, while the
configuration guide specifies 24.04. Ubuntu ended 25.10 support on July 9, 2026.
The November 18 setup run published a sandbox image. Its install job encountered
a separate PostgreSQL major-version mismatch. Services recovered on a fresh
18.6 volume, with the old 17 volume retained. Determine which old rows need
migration under #38 and verify the selected sandbox digest under #70 before rollout.
[Release Dockerfile](../packages/boxie/sandbox/Dockerfile) ·
[Integration Dockerfile](../packages/boxie/tests/integration/Sandbox.Dockerfile) ·
[Ubuntu release notice](https://lists.ubuntu.com/archives/ubuntu-announce/2026-July/000325.html) ·
[Image build](https://github.com/di-rs/sanctuary/actions/runs/44368902909/job/135030138660) ·
[Incident and recovery](https://github.com/di-rs/sanctuary/pull/309)

## Simplification task

- [ ] **Share GitHub request handling across the publishers.** The benchmark
  and preview scripts contain seven identical definitions for requests, bounded
  reads, JSON validation, authentication and pagination. The two 188-line
  transport test files differ only in which publisher they import. The binary-size
  reporter also imports the benchmark transport. [Benchmark publisher](../tools/cli-bench/report.py) ·
  [Preview publisher](../tools/cli-playground/preview_ci.py) · [Size reporter](../tools/cli-bench/size_report.py)

Move those definitions and their limits to a checkout-local module under
`tools/`. Keep each publisher's revision, pull-request state, artifact and
permission decisions in its existing controller. Parameterize the common tests
over both entry points. Exercise `preview_ci.py`, `report.py --kind bench` and
`report.py --kind size` from a different working directory in their respective
tests. Verify bounded responses, timeouts, pagination, credential redaction and
stale-revision handling before removing the copies. [Benchmark policy tests](../tools/cli-bench/tests/test_github_policy.py) ·
[Preview policy tests](../tools/cli-playground/tests/test_infra_workflows.py)

## Follow-up cleanup

Apply these gates when the affected work comes up. The first two protect shared
Boxie state. The next two belong to the preview publisher and gateway.

| Priority and timing | Owner and change | Evidence to finish |
| --- | --- | --- |
| P1 before changing admission or persistence | Boxie, shared infrastructure and binary-size maintainers should assign the 47 Python integration cases that no workflow selects. Of 292 collected cases, the gap covers 44 Boxie cases, two shared-host observability cases and one binary-size case. It includes 33 of the 34 parametrized Boxie PostgreSQL cases. [CI selection](../.github/workflows/boxie-lifecycle.yml) · [Integration launcher](../packages/boxie/tests/run_integration.py) | Compare collected test IDs with the union selected by workflow jobs. Assign each to a runner with the needed services or document its operator-only prerequisite. Run admission, concurrency and migration cases on the production PostgreSQL major. |
| P1 before admitting a second independent Boxie consumer | Boxie's artifact owner should reserve retained expanded bytes and object counts per consumer and across the installation. Each upload is bounded today, but valid active artifacts accumulate on the volume shared with Docker. [Artifact store](../packages/boxie/src/boxie/persistence/postgres_artifacts.py) · [Host storage](../infra/host/bootstrap.sh) | Use small test quotas. Account for staging and existing artifacts, charge exact retries once, preserve another consumer's capacity, and release the reservation after physical collection succeeds across restart. |
| P1 before the next catalog-enabled playground rollout | Serve the revision catalog on the owning preview hostname. In a local PostgreSQL-backed test, the control hostname returned 200 and the returned PR hostname gave 404 for the same revision. [Host filter](../tools/cli-playground/src/cli_playground/transport.py) · [Catalog route](../tools/cli-playground/src/cli_playground/routes.py) | Cover the control host, the owning preview and a sibling in one test. The owner gets its catalog, the sibling gets 404, and a legacy binary-only revision returns JSON null on its own host. |
| P2 with the publisher simplification, before expanding upload limits | Guard ZIP directory bytes and member count before the publisher or gateway opens a preview bundle. Both check the count after Python allocates the member table. Boxie already has a bounded preflight. [Preview reader](../tools/cli-playground/src/cli_playground/artifacts.py) · [Boxie preflight](../packages/boxie/src/boxie/persistence/zip_metadata.py) | With small configured limits, prove rejection occurs before the ordinary parser runs. Preserve support for valid executable bundles with and without a catalog, and keep each application's packaging independent. |

The remaining work fits the next maintenance pass for each owner.

| Priority and trigger | Change | Acceptance |
| --- | --- | --- |
| P2, next preview catalog change | Use the same Cargo package discovery on both revisions. The baseline searches only `buildins/` and `packages/`, so comparing `cli-testing` in `tools/` with the identical commit labeled it added. [Baseline discovery](../tools/cli-playground/src/cli_playground/catalog_build.py) | An unchanged or moved tool compares against its old binary. A genuinely new CLI is added. An unreadable or unbuildable baseline yields an unavailable comparison. |
| P2, before relying on unattended stop recovery | Let the playground settle a pending stop when its original Boxie consumer can no longer find a previously bound sandbox. In a local test, Boxie purged a settled record aged past seven days. Two gateway retries left the stop pending. [HTTP client](../tools/cli-playground/src/cli_playground/boxie_client.py) · [Retry loop](../tools/cli-playground/src/cli_playground/service.py) | Preserve the request ID, retry timeouts and 5xx, and surface credential failures. A 404 can conceal another owner's ID. Settle only a previously bound operation for its original consumer, recording its absence without inferring a terminal reason. Restart and closed-preview cleanup leave it settled. |
| P2, before using dependency audits as release evidence | The Python and frontend audit workflows report scanner timeouts in their summaries but exit successfully. The Python workflow also accepts an empty dependency report for the nonempty lockfile. [Python audit](../.github/workflows/python-audit.yml) · [Frontend audit](../.github/workflows/frontend-audit.yml) | Show clean, affected and incomplete results distinctly. Check that applicable dependencies were examined. Cover empty results and an unavailable scanner, and explicitly decide which outcomes block release. |
| P2, before using Shish on a shared Unix host | Create new command-history files with owner-only permissions. Explicit writes and exit saving use the pinned Brush implementation's ordinary file creation mode. On a traversable path, the umask can allow other local users to read command arguments. [History adapter](../packages/shish/src/history.rs) · [History behavior](../packages/shish/README.md) | Explicit write, append and interactive exit create a new file with mode 0600 under a permissive umask. Existing private files retain their permissions. |
| P2, next grepr maintenance change | Match the contents of each line while preserving its original output bytes. An independent grep selected both newline-terminated `alpha` records for `^alpha$`. Grepr selected neither and also missed blank lines for `^$`. [Matcher](../buildins/grepr/src/lib.rs) | Compare record selection and counts in ordinary and inverted modes for terminated, empty and final unterminated lines. Check grepr's output bytes and exit behavior separately. |
| P2, next fixture-runner change | Report paths already written on every I/O failure during a multi-file fixture promotion. Destination resolution and reads can currently bypass the diagnostic used for write failures. [Promotion loop](../tools/cli-testing/src/recording.rs) · [CLI contract](../tools/cli-testing/README.md) | Induce a failure after the first replacement in a temporary suite. The error names the committed path and the failing destination, and a retry is predictable. |
| P2, next playground storage cleanup | Fetch pending artifact IDs and their saved request IDs in one query. The retirement loop currently opens another database session for each ID it just selected. [Retry loop](../tools/cli-playground/src/cli_playground/service.py) · [Retirement queries](../tools/cli-playground/src/cli_playground/session_store.py) | A batch uses one read for both values. A failed retirement still retries with its original request ID and marks completion only after Boxie acknowledges it. |
| P2, if slow storage delays the gateway | Measure event-loop responsiveness during upload writes and staging cleanup. If confirmed, reuse the existing cancellation-safe staging worker for the blocking operations. [Gateway](../tools/cli-playground/src/cli_playground/service.py) · [Staging worker](../tools/cli-playground/src/cli_playground/upload_staging.py) | On a deliberately slow test filesystem, another metadata or terminal request completes during an upload. Cancellation and recovery retain the correct staged bytes and upload intent. |
| P3, next CLI maintenance pass | Check for out-of-tree users of the dormant grepr manpage script and lsr permission helper. Remove unused files and Parsu's obsolete nested lockfile in small owner-specific changes. [Grepr script at review](https://github.com/di-rs/sanctuary/blob/fa91aa905c728c15232e95a1ab7d2b0e2bbaa1ce/buildins/grepr/_build.rs) · [Lsr fixture setup](../buildins/lsr/tests/cli.rs) · [Obsolete lockfile](https://github.com/di-rs/sanctuary/blob/fa91aa905c728c15232e95a1ab7d2b0e2bbaa1ce/packages/parsu/Cargo.lock) | The root locked Cargo metadata and affected CLI checks still pass. Lsr permission fixtures work from a clean checkout on both supported test platforms. |
| P3, next provisioning change | Determine whether any operator still uses the playground's standalone Pulumi host entry point alongside the shared-host stack. Record its owner and state before considering retirement. [Playground entry point](../tools/cli-playground/infra/__main__.py) · [Shared host](../infra/environments/single-host/stack.py) | Each active stack has a supported entry point. Any proposed retirement demonstrates a Pulumi preview with no unintended replacement of protected resources. |

Two P3 changes need a decision about CLI behavior. Lsr's long listing follows
links before testing whether the entry is a link. When simplifying that formatter,
use the collected metadata once and cover existing and dangling links. A
streaming rewrite of `uniqr` would change when output appears on a late input
error. Keep #318 focused on file identity and decide that behavior if memory
use on long inputs warrants a separate change. [Lsr formatter](../buildins/lsr/src/lib.rs) ·
[Uniqr grouping](../buildins/uniqr/src/lib.rs)

Shish's 15 ignored compatibility cases already have a package-owned inventory.
Use it when selecting a shell behavior. An approved Shish sandbox profile needs
native terminal and isolation evidence. Biggie, Kara, Parsu and the standalone
commands can keep their own release and maintenance schedules.
[Shell compatibility](../packages/shish/docs/compatibility.md) · [Shish integration stages](../packages/shish/docs/durability.md)

## Review coverage

The November 18, 2026 review inventoried every tracked entry at
[`fa91aa90`](https://github.com/di-rs/sanctuary/tree/fa91aa905c728c15232e95a1ab7d2b0e2bbaa1ce).
The 1,345 entries include fixtures, generated binaries, lockfiles, automation
and a symlink fixture. Run `git ls-tree -r --name-only fa91aa90` to reproduce
the inventory.

| Surface | Tracked entries | Evidence |
| --- | ---: | --- |
| Builtins and shared crates | 641 | All 26 workspace Rust packages and 22 binary targets were covered across this row, applications and tools. On Apple Silicon macOS, 1,151 enabled native tests passed, including a targeted rerun for a Unix socket. Nextest ignored 21 cases. Eight doctests passed and four were ignored. Formatting, all-target Clippy and package policy passed. Of 541 catalog cases, 404 matched independent references, 133 matched manual expectations and four used native tests. |
| Applications | 355 | Boxie, Biggie, Kara, Parsu and Shish. Boxie passed all 297 portable tests and 145 of its 152 integration cases locally, including PostgreSQL, real Temporal, job recovery under `runc`, isolated wheel installation and Compose checks. Six cases require Linux/amd64 with gVisor and one requires host journald. Both packaged Linux capture binaries matched fresh builds. |
| Tools, infrastructure and GitHub automation | 299 | 235 tool files, 25 infrastructure files and 39 GitHub files. Locally, 711 of 712 tests in the tools/infra Python scope passed. The remaining case requires native Linux/amd64 and gVisor. The frontend production build, 76 frontend unit tests, Chromium scenarios against the test transport, actionlint and ShellCheck passed. |
| Workspace root and supporting files | 50 | Reviewed project direction, architecture, contributor guidance, skills, development environment, lint policy and lockfiles. Locked Cargo metadata, the uv lock check, strict mypy across 312 Python sources and offline documentation links passed. |

On the audited revision, the hosted job-recovery, PostgreSQL/Temporal and
journald checks passed. The shared Linux/gVisor run passed five of seven native
scenarios. One timed out before uploading an artifact because its test expected
a 30-second collector schedule. Production runs that schedule every 12 hours.
The playground test saw a connection reset while publishing its first preview
immediately after container startup. [Boxie native job](https://github.com/di-rs/sanctuary/actions/runs/44392799874/job/135114636267) ·
[Shared browser baseline](https://github.com/di-rs/sanctuary/actions/runs/44391167602/job/135108903205)

The corrected harness starts the real collector during the held upload
acknowledgement and waits for that workflow after supervisor restart. The
browser test polls the gateway health endpoint before submitting the preview
once. The terminal smoke test clears its Bash command-start marker so its
byte comparison sees only command output. All seven shared Linux/gVisor scenarios
passed on `ff9c0235`, including the browser reconnect to the original session.
[Native verification](https://github.com/di-rs/sanctuary/actions/runs/44397323245/job/135130756093) ·
[PostgreSQL and Temporal recovery](https://github.com/di-rs/sanctuary/actions/runs/44397297060/job/135130503493)

### Workflow and component checks

The follow-up on `ff9c0235` mapped 31 workflow definitions and 63 declared
jobs. Before the additional maintenance run, 12 workflows had passed on that
commit and 18 had run on other revisions. The remaining definition is the
reusable image builder, invoked seven times by three workflows. All three
completed-run triggers name existing producers. All 131 external action
references use full commit IDs. Release, setup and badge publication were
reviewed through their existing run records and source. The maintenance workflow
also exercises release-mode Rust, stable/beta/nightly, coverage and Miri.
[Workflow definitions](../.github/workflows) ·
[Maintenance run](https://github.com/di-rs/sanctuary/actions/runs/44401106267)

The 22 real CLI executables exported 56 commands and 233 arguments accepted by
both the gateway and the frontend. All 43 package demo recipes ran locally
against Boxie's six sample files, including a Kara terminal edit and save.
The native browser scenario exercises a binary-only preview on loopback.
Catalogs on the production-style hostname need their own coverage.
[Catalog builder](../tools/cli-playground/src/cli_playground/catalog_build.py) ·
[Browser fixture](../tools/cli-playground/tests/test_native.py)

Fifty-five Boxie and playground database tests passed with the production-pinned
PostgreSQL 18.6 image. A separate local restore moved all three databases from
17.11 to a fresh 18.6 cluster after quiescing writers. It recovered the artifact
bytes and owner, two jobs with their reservations and submission keys, and an
11-event Temporal workflow. A new Temporal workflow completed after restore.
An off-host restore, supervisor journal reconciliation and fencing, a new sandbox
job, a backup-failure alert and the selected production image digest still need
operator evidence. [Restore drill](https://github.com/di-rs/sanctuary/issues/38) ·
[Sandbox release](https://github.com/di-rs/sanctuary/issues/70)

## Existing GitHub work

At the start of triage GitHub had seven open issues, seventeen closed issues and
nine open PRs. The seven open issues appear in the queue above. The two
reproduced data-loss defects were the only new issues.

Five closed issues were marked completed. They delivered playground argument
discovery (#35), playground PostgreSQL storage (#71), job recovery (#300), the
generated CLI index (#301) and executable README examples (#302). The other
twelve were closed as unplanned (#9, #10, #12 and #15–#23). The repository
subsequently shipped a bounded benchmark runner and native previews. Cross-run
benchmark history and the original browser-WASI design would need fresh
requirements. [Benchmark runner](https://github.com/di-rs/sanctuary/pull/13) ·
[Native previews](https://github.com/di-rs/sanctuary/pull/32)

| Open PRs at review | Priority and next action |
| --- | --- |
| [PostgreSQL 18.6 to 18.7](https://github.com/di-rs/sanctuary/pull/311) | P1 before rollout. The persistence check requested a High risk selection, production impact, existing-data validation and recovery. Supply the rehearsal and rollback evidence on the existing PR. |
| [Rust toolchain #310](https://github.com/di-rs/sanctuary/pull/310), GitHub Actions [#312](https://github.com/di-rs/sanctuary/pull/312), [#313](https://github.com/di-rs/sanctuary/pull/313), [#314](https://github.com/di-rs/sanctuary/pull/314), [#315](https://github.com/di-rs/sanctuary/pull/315), [Cargo #316](https://github.com/di-rs/sanctuary/pull/316) and [uv #317](https://github.com/di-rs/sanctuary/pull/317) | P2 on the normal dependency schedule. The checks passed at review. Inspect the pins and changelogs, particularly the major action upgrades in #312 and #314, and verify their affected jobs before merge. [Dependency maintenance](dependency-updates.md) |
| [Weekly scan draft](https://github.com/di-rs/sanctuary/pull/91) | P3 when maintainers want the recurring scan and have an owner for its credential, cost and reports. Evaluate its manual run in the existing draft. |
