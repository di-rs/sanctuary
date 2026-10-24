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
Missing or conflicting choices leave that family unlabelled. Correct the
checkboxes and save the description to update the labels. Classification does not
block merging or infer a risk level.

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

The bot applies every matching area from changed paths, including deleted files.
Renames match their new path. These identify directly changed components, not
every transitive consumer. Describe consumer effects and validation in the PR body.

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
live in [the label rules](.github/labeler.yml).

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

[Multi Labeler](https://github.com/fuxingloh/multi-labeler) applies
[the YAML rules](.github/labeler.yml) through a pinned GitHub Action. There are no
repository scripts, installed tools, or local commands to run. Labels with
`sync: true` are removed when their rule no longer matches; labels outside the
configuration, including `run-ci`, are preserved.

Create new labels with descriptions and colors in GitHub's Labels settings, then
add their rules and template choices in a PR. Type and risk rules require exactly
one checked choice inside their template group. Impact rules allow multiple
choices, with `impact:none` selected alone. Dependabot's author rule supplies only
`type:dependencies`; its risk still needs reviewer assessment.

The workflow uses `pull_request_target`, so configuration comes from the trusted
base revision, including for fork PRs. It does not check out or run PR code, post
comments, or add merge checks. It starts working after merge into the default
branch. Dependency updates to the pinned action require normal review.

The action uses the event's PR description and GitHub's changed-file API, which
returns at most 3,000 files. For larger PRs, area labels may be incomplete. It
matches renamed files at their new path; describe effects on the old component in
the PR body. If labels look stale after rapid edits or an API failure, save the
current description again to trigger a fresh event. Inspect the action logs for
failures; removal errors can require a manual label correction.

There is no bulk migration of existing PR labels or scheduled processing of old
PRs. The workflow handles only the PR that triggered its event.
