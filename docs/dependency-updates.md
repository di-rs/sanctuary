# Maintain dependencies

GitHub Dependabot opens weekly update pull requests using
[the repository configuration](../.github/dependabot.yml). Review each diff and
its CI results before merging. Merging image updates changes the committed
deployment inputs; operators still run setup, releases, and database migrations
explicitly. See [releases and recovery](../infra/docs/releases.md).

## Automated coverage

| Dependencies | Source | Update grouping |
| --- | --- | --- |
| Rust crates | Cargo workspace manifests and lockfile | Minor/patch updates together; majors separate |
| Python packages | uv workspace manifests and lockfile | Minor/patch updates together; majors separate |
| Frontend packages | Frontend package manifest and pnpm lockfile | Minor/patch updates together; majors separate |
| GitHub Actions | Workflow action references | Individual updates |
| Container images | Listed Dockerfile and Compose directories | One group across both ecosystems |
| Rust toolchain | `rust-toolchain.toml` | One open toolchain PR at a time |

The container group keeps repeated references together, including Vector's
collector and storage initializer and Temporal's server and schema tools.
It can contain major upgrades, so review the release notes and migration needs
of every changed service. Tests require matching Temporal server/schema versions
and matching Vector source images.

Keep upstream image versions beside their immutable digests as
`image:version@sha256:digest`. Compose files and Dockerfiles own those pins;
integration tests read them directly. Local image defaults and operator-selected
application images are not upstream dependencies.

When adding a Dockerfile or a Compose service with an upstream image, add its
directory to the corresponding Dependabot entry. GitHub's native managers support
the repository's `*.Dockerfile` and `compose.*.yml` filenames. Review the job logs
under **Insights → Dependency graph → Dependabot** after configuration changes;
they show discovery, registry, and lockfile-generation failures. See
[GitHub's supported ecosystems](https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories).

## Pins that need manual updates

Dependabot coverage does not include arbitrary version strings or download
checksums. Update these deliberately:

- Release downloads in workflows, including actionlint and lychee: update the URL
  and SHA-256 together and verify the downloaded archive.
- The Grafana plugin in
  [plugins.json](../packages/boxie/infra/observability/plugins.json): update the URL
  and checksum together. Setup reuses an existing plugin directory, so follow the
  [plugin installation instructions](../packages/boxie/docs/observability.md#configure-grafana)
  when replacing an installed version.
- Tools selected through workflow inputs or environment variables, including uv,
  Pulumi, Gitleaks, and tools installed by `taiki-e/install-action`; minimum tool
  versions in workspace/hook configuration; Python and Node version files; and
  Temporal test-server pins. A package or Action update does not update these pins.
- Host packages and copied skill sources, using their owning maintenance process.

Dependency alerts and security updates remain GitHub features. The scheduled
[maintenance workflow](../.github/workflows/maintenance.yml) also runs Rust
vulnerability and license checks. Neither replaces reviewing dependency PRs.
