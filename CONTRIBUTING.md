# Contributing to Sanctuary

Describe the problem, final behavior, risk, impact, and completed validation in
[the PR template](.github/pull_request_template.md). Choose the classification
checkboxes before requesting review. You can edit your PR description to change
those choices without having permission to apply GitHub labels directly.

Follow [AGENTS.md](AGENTS.md) for branch names, Gitmoji commits, package ownership,
and verification. Run affected packages' tests and linters; CI runs the full checks.

## Classify your change

Choose exactly one primary type and one risk level. Select all relevant impacts,
or select `impact:none` alone. Keep the checkbox markers and label names intact.
The automation reads only these groups, not labels mentioned elsewhere in prose.
Missing or conflicting selections appear in the PR classification workflow summary;
they do not block merging or cause the bot to guess a risk level.

### Primary type

| Label | Choose it for |
| --- | --- |
| `type:feature` | New or extended supported behavior |
| `type:fix` | Correcting incorrect behavior |
| `type:refactor` | Restructuring implementation without intended behavior changes |
| `type:performance` | Improving runtime, memory use, or throughput |
| `type:docs` | Documentation-only changes |
| `type:tests` | Tests, fixtures, or reference generators only |
| `type:dependencies` | Dependency or lockfile updates |
| `type:maintenance` | CI, packaging, development tooling, or repository policy |

Choose the purpose of the PR. A bug fix with regression tests is `type:fix`.
Dependency bots receive `type:dependencies`; a reviewer still assesses their risk.

### Risk

| Label | Consequences if the change is incorrect |
| --- | --- |
| `risk:low` | Narrow, readily reversible, and limited in impact |
| `risk:medium` | Runtime, parsing, output, dependency, shared-library, or tooling behavior with bounded impact |
| `risk:high` | Potential data loss, permissions or authentication failures, sandbox escape, privileged publication/deployment, or difficult recovery |

Keep a concrete reason in **Risk Assessment**. Risk depends on consequences, not
patch size: a small atomic-save change can be high risk. Missing test evidence is
a verification gap, not a separate risk level. A low-risk label does not establish
merge readiness.

### Impact

| Label | Review obligation |
| --- | --- |
| `impact:breaking` | Explain incompatible flags, output, exit codes, APIs, schemas, or configuration and the migration path |
| `impact:security` | Review the affected permissions, authentication, isolation, or sensitive data controls against the [threat model](docs/thread-model.md) |
| `impact:persistence` | Verify saved files, history, databases, storage formats, and recovery behavior |
| `impact:performance` | Supply benchmark evidence for hot-path changes or performance claims, or explain why it is unavailable |
| `impact:cross-platform` | Verify affected OS-dependent filesystems, permissions, signals, terminals, and platform APIs |

`impact:none` is a template choice, not a GitHub label. Impact labels identify
work that needs review; they do not certify that verification has passed.

### Affected areas

The bot applies every matching area from changed paths, including old paths for
renames and deleted files. These identify directly changed components, not every
transitive consumer. Describe consumer effects and validation in the PR body.

| Labels | Paths |
| --- | --- |
| `area:biggie`, `area:boxie`, `area:kara`, `area:parsu`, `area:shish` | Matching application directories under `packages/` |
| `area:builtins` | `buildins/` |
| `area:shared-libraries` | `utils/` |
| `area:playground` | `tools/cli-playground/` |
| `area:benchmarks` | `tools/cli-bench/` |
| `area:repo-tooling` | Repository checks, label tooling, agent instructions, and development configuration |
| `area:infrastructure` | Root or component-owned infrastructure, Dockerfiles, and Compose files |
| `area:ci` | GitHub workflows, actions, rulesets, and Dependabot configuration |
| `area:workspace` | Root manifests, lockfiles, and workspace/toolchain settings |
| `area:docs` | Markdown files and documentation directories |

A Boxie deployment guide receives `area:boxie`, `area:infrastructure`, and
`area:docs`. Name individual builtins in the PR description. The exact mappings
live in [the label catalog](.github/labels.yml).

## Examples

| Change | Contributor choices |
| --- | --- |
| Shish documentation correction | `type:docs`, `risk:low`, `impact:none` |
| Kara atomic-save permission fix | `type:fix`, `risk:high`, `impact:persistence`, `impact:security`, `impact:cross-platform` |
| Playground flag-search fix confined to filtering displayed rows | `type:fix`, `risk:low`, `impact:none`, with the affected interaction and browser regression explained |
| Shared test-harness behavior change | `type:maintenance`, `risk:medium`; identify affected consumers and their test results |

## Review and CI

Classification labels describe changes; they do not express merge readiness.
Reviewers assess the current diff, test evidence, and required checks before
merging. For stacked PRs, review the intended parent and merge order.

Apply `run-ci` manually to request existing CI on a draft. Template selections
cannot request it. Other label additions skip expensive CI jobs and use separate
concurrency groups so they cannot cancel useful runs. Their skipped checks have
distinct names so they cannot replace required check results. Benchmark selection still
depends on changed Rust source/build files, not labels.

## Maintain the label system

[The catalog](.github/labels.yml) owns names, descriptions, colors, ownership, and
path mappings. It uses JSON syntax, which is also valid YAML, so the controller
needs only Python's standard library. Author-owned labels come from the template;
path-owned labels come from the diff. Edit the PR description to correct an
author-owned label: manual changes are overwritten at the next reconciliation.

The controller reads all changed-file pages and refuses a partial classification
if GitHub's file count does not match. It retries when metadata changes during
inspection. Rerun the classification workflow after an API failure. Existing issue
labels, ecosystem labels, `run-ci`, and unrelated custom labels are preserved.

From the repository root, use Python 3.11 or newer and an authenticated `gh`
installation. These commands default to dry runs and print JSON:

```sh
GH_TOKEN="$(gh auth token)" python3 tools/pr-labels/pr_labels.py sync --repo di-rs/sanctuary
GH_TOKEN="$(gh auth token)" python3 tools/pr-labels/pr_labels.py reconcile --repo di-rs/sanctuary --pr 123
```

Add `--apply` to write the reviewed changes. Catalog synchronization creates or
updates declared labels and never deletes unrelated labels. Run it before enabling
the workflow or adding new labels to the template. It needs repository label-write
permission; routine PR reconciliation only needs contents-read and PR-write access.

There is no bulk migration of existing PR labels. Reconciliation handles one PR
at a time, on workflow events or an explicit maintainer invocation.

The metadata workflow runs trusted default-branch code and never installs or
executes PR code. It operates on forks and stacked PRs without changing their
branches. It becomes active after its workflow and controller reach the default
branch. Changes to this controller require review of that trust boundary.
