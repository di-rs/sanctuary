# Dependency updates

[Renovate](https://docs.renovatebot.com/) proposes dependency updates using the
[root configuration](../../renovate.json). The
[validation workflow](../../.github/workflows/dependency-updates.yml) checks the
configuration, extracts dependencies with Renovate, and simulates custom pin
updates in a temporary directory. CI also downloads the pinned release assets
and verifies their SHA-256 checksums. It does not open PRs or deploy services.

## Activate the bot

A repository administrator must install or authorize the
[Renovate GitHub App](https://github.com/apps/renovate) for `di-rs/sanctuary`.
Authorize it before merging the migration that removes Dependabot's version-update
configuration. After merging, check the **Dependency updates** issue for detected
dependencies, lookup failures, and pending PRs. The first hosted run is required
to confirm registry access and lockfile generation; local extraction tests cannot
prove those operations will succeed in the hosted service.

Keep GitHub's dependency graph and Dependabot alerts enabled in repository security
settings. Removing `dependabot.yml` stops its configured version-update jobs; it
does not turn off alerts. Use Renovate for routine update PRs to avoid two bots
opening the same upgrades.

PR creation is allowed daily from midnight through 06:59, Europe/Paris, subject to
the hosted app's run frequency. The limit is two new PRs per hour and ten open PRs.
Rust nightly updates and lockfile maintenance have a Monday window. Automatic
merging is disabled. PostgreSQL and Temporal server major upgrades require approval
in the dependency dashboard before a PR is created.

## Coverage

| Dependency | How it is tracked |
| --- | --- |
| Cargo crates, Python workspace packages, frontend packages | Built-in managers, with Cargo, uv, and pnpm lockfiles |
| Dockerfiles and Compose images, including test images | Built-in managers; explicit tags and immutable digests |
| GitHub Actions and supported tool inputs | Built-in manager; commit pins have version comments |
| Rust nightly, `.python-version`, `.node-version` | Built-in toolchain managers |
| Monitoring and Temporal image inventories | Custom rules update each version and image digest together |
| Grafana logs plugin, lychee, actionlint | GitHub release-attachment rules update versions and SHA-256 checksums together |
| Rust CI tools, Gitleaks, Pulumi CLI, minimum uv/prek versions | Custom rules for their pinned values |
| Renovate validation runtime | The npm manager tracks its locked validation package |

Related updates for Temporal server/schema tools, uv, Pulumi, and Vite Plus are
grouped. Other minor and patch library updates are grouped by ecosystem; major
updates remain separate. The same image name is used in inventories and consuming
manifests so Renovate can update those occurrences in one PR. CI rejects version
or digest disagreement between them.

Version records describe current pins. Historical verification dates, child
manifest digests, and bundled component versions are not evidence for a newly
selected image, so they are not maintained as current inventory fields. Git history
retains the previous observations. Grafana's bundled Prometheus plugin follows the
Grafana image; only the separately downloaded logs plugin has its own update rule.

Host packages installed through APT, running containers, database migrations,
operator-supplied application image digests, and copied upstream code in skills
remain outside this bot's update coverage. Applying an image update still requires
the appropriate [deployment operation](../../infra/docs/releases.md). Temporal and
PostgreSQL updates need their own migration review. A plugin archive update also
needs an installation review: setup currently reuses an existing plugin directory.

## Validate a change

Run from the repository root with Node.js 24.15 or later in the 24.x series and npm:

```sh
npm ci --prefix tools/dependency-updates --ignore-scripts
npm rebuild --prefix tools/dependency-updates re2
npm run --prefix tools/dependency-updates check
```

Success ends with `Dependency coverage, replacement, and image consistency checks
passed.` The check uses Renovate's internal APIs, so a Renovate runtime update must
pass this check before merging. It verifies extraction and replacement without
fetching newer versions or changing repository files. Run
`npm run --prefix tools/dependency-updates check:assets` to also download and hash
the three separately pinned release assets; this requires network access.

When adding a pin, prefer a supported manifest. For custom formats, add a matching
rule and a coverage assertion in [check.mjs](check.mjs). Keep image version fields
adjacent to their image references and keep full release tags in asset records.
New tools in `taiki-e/install-action` inputs must be recognized by a custom rule;
the check fails if one is missed. Inspect the hosted dependency dashboard after
merging new rules to catch registry or release-naming problems.
