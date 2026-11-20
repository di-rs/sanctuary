# Deploy CLI playground

## Production

The `cli-playground` Dokku app serves the built frontend and one gateway worker
on the same Hetzner VM as Boxie. The gateway owns upload recovery and its local
staging directory. Keep one web process per app. During a release Dokku stops
that app's old process before starting its replacement, which briefly interrupts
that app's connections. Boxie owns sandbox execution and has a separate release.

After [host setup](../../../infra/docs/setup.md), deploy current `master` from
an authenticated operator checkout with one command.

```sh
gh workflow run cli-playground-release.yml --ref master
```

Actions builds the image and streams it to the pinned SSH host. The release
applies Alembic, deploys the local image with Dokku, then checks public HTTPS
and authenticated Boxie readiness. Production keeps its PostgreSQL database,
upload volume and wildcard TLS certificate across releases. Traefik is the public
listener. The Dokku manager and Boxie have no public ports.

## Playground app previews

A PR that changes the frontend, backend, or their build inputs gets a GitHub
deployment named `cli-playground/feature-pr-N`. Open **View deployment** on the PR
to try that revision at `app-pr-N.<playground-domain>`. Its terminal includes
`echor` from the trusted base checkout. A PR that also changes a CLI gets the
usual [CLI binary preview](previews.md) at `pr-N.<playground-domain>`.

Each feature app has its own PostgreSQL instance, upload storage, publisher token
and Boxie consumer. A push updates the same URL. Closing the PR or removing its
Playground changes destroys its app and revokes its token. Reopening an eligible
PR recreates it. The [feature workflow](../../../.github/workflows/cli-playground-feature.yml)
uses the existing `cli-playground` SSH environment.

Feature storage is disposable. A database container restart clears that preview's
database. Rerun its feature workflow to migrate and seed it again. The shared host
accepts three simultaneous app previews by default. A full host reports capacity
in the workflow. After a slot becomes available, rerun the current PR workflow.
To change capacity, set the desired count in
`/etc/sanctuary/playground-apps/limit` on the host. Each preview has a 384 MiB
gateway and a 320 MiB database limit, in addition to its Boxie terminal workload.

To reconcile an existing PR or retry after a host restart, supply its number.
The workflow reads the current commit and open or closed state from GitHub.

```sh
gh workflow run cli-playground-feature.yml --ref master -f pr=123
```

## Independent local unit

Obtain a private Boxie URL and consumer credential from its operator; see
[Boxie infrastructure](../../../packages/boxie/docs/deployment.md). Boxie owns its
default shell, sandbox image and built-in sample files. cli-playground uploads
validated native binaries and requests a sandbox using only their artifact ID.
It does not select an environment or modify Boxie's configuration.

Run from the repository root:

```sh
docker build -f tools/cli-playground/infra/docker/CliPlayground.Dockerfile -t cli-playground:local .
```

From the repository root, create an external product-data volume and set the
consumer connection. The network must already exist; it can belong to a separate
Boxie installation. There is no cross-project `depends_on`.

```sh
docker volume create cli-playground-data
export CLI_PLAYGROUND_PROJECT_NAME=cli-playground
export CLI_PLAYGROUND_DATA_VOLUME=cli-playground-data
export CLI_PLAYGROUND_CONSUMER_NETWORK=boxie-consumers
export CLI_PLAYGROUND_DATABASE_NETWORK=boxie-postgres_playground
export CLI_PLAYGROUND_DATABASE_URL_FILE=/private/path/playground-database-url.secret
export CLI_PLAYGROUND_BOXIE_URL=http://boxie-api:8090
export CLI_PLAYGROUND_BOXIE_CREDENTIAL_FILE=/private/path/consumer.secret
export CLI_PLAYGROUND_DEPLOY_TOKEN=local-deploy-token
export CLI_PLAYGROUND_PUBLIC_URL=http://localhost:8000
docker compose -f tools/cli-playground/infra/compose.yml run --rm --no-deps backend \
  alembic upgrade head
docker compose -f tools/cli-playground/infra/compose.yml up --build -d
```

Both local and production manifests default to project `cli-playground`. Override
`CLI_PLAYGROUND_PROJECT_NAME` for another installation; keep it distinct from Boxie's
`BOXIE_PROJECT_NAME` (default `boxie`). Do not give the two units a shared
`COMPOSE_PROJECT_NAME` or `--project-name`, which overrides the manifest identity.
Their external network and volume identifiers remain independently configured.

The consumer credential must be a regular non-symlink file, mode `0600`, containing a
16–4096-character printable token. The local unit publishes only localhost:8000.
Boxie's artifact data and supervisor
credential never enter cli-playground. Runtime images contain only their own installed
package/dependencies and, for cli-playground, its real built frontend assets.

Operator modules are installed separately from runtime images. Run
`uv sync --all-packages` for local infrastructure checks. Application
release jobs use native OpenSSH and do not read Pulumi state.
