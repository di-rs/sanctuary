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

## Order of work

Take one row at a time. P0 means immediate work to prevent demonstrated data
loss. P1 covers the next cleanup or a release or operations gate. P2 follows
baseline cleanup. P3 needs an identified user and capacity for optional work.
Two gates have their own timing. Complete the notices work before distributing an
affected artifact and the restore drill before relying on production state.
Development and local verification can proceed independently of both gates.

| Order | Priority | Work and timing | Evidence to finish |
| --- | --- | --- | --- |
| 1 | P0 | Fix `uniqr` before its next distribution. A 14-byte file passed as both redirected stdin and named output was truncated to zero with exit 0. [#318](https://github.com/di-rs/sanctuary/issues/318) | Compare the open input and output before truncation. The same path, a hard link and a symlink each return 65 and preserve the input. Pipes and distinct destinations still work. |
| 2 | P0 | Fix Kara's save behavior before its next distribution. Ctrl-S on a clean buffer replaced text saved by a second writer. [#319](https://github.com/di-rs/sanctuary/issues/319) | A clean save preserves the external change. A dirty buffer detects a change completed before save, retains edits and allows Save As. Cover both writers through the terminal. |
| 3 | P1 | Finish the fixed Boxie environment before the next sandbox publish or rollout. Interactive creation already accepts an artifact ID, and the naming cutover is complete. [#70](https://github.com/di-rs/sanctuary/issues/70) · [Original implementation](https://github.com/di-rs/sanctuary/pull/74) · [Cutover cleanup](https://github.com/di-rs/sanctuary/pull/76) | Restore the documented supported base in both sandbox Dockerfiles. Move playground packaging and shared-host assertions to their owners. Prove Boxie's build and standalone tests with consumer sources absent, then exercise upload, attach, reconnect and cleanup with Linux/gVisor. |
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
[Preview policy tests](../tools/cli-playground/tests/test_preview_github_policy.py)

## Follow-up cleanup

These items can be picked up in the named component's next maintenance pass.
Keep them here until their trigger is met.

| Priority and trigger | Change | Acceptance |
| --- | --- | --- |
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
byte comparison sees only command output. The default-environment issue tracks
the hosted verification of these checks. A fresh-host restore and the selected
production image digest require operator evidence.
[Native verification and remaining release work](https://github.com/di-rs/sanctuary/issues/70)

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
