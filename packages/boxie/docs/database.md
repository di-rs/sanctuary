# PostgreSQL for Boxie

This Compose project stores Boxie's sandbox state and Temporal's persistence and
visibility databases. Each service has its own database and non-superuser login.
Only the provisioning credential is a PostgreSQL administrator.

## Start a fresh database

The Sanctuary PostgreSQL project runs one cluster. Boxie owns its database through a dedicated login. Temporal and the gateways each use their own roles. The host controller provisions this ownership before running application migrations. [PostgreSQL deployment](../../../infra/services/compose.postgres.yml) · [First deployment](../../../infra/docs/setup.md)

## Apply Boxie migrations

Using the installed Boxie environment and its private DSN file:

```sh
python -m boxie.persistence.migrate --dsn-file /run/secrets/boxie-dsn
```

Migration sources live in `packages/boxie/alembic/`, alongside `alembic.ini`, and
are included in the installed package. From the repository root, use
`uv run --package boxie python -m boxie.persistence.migrate --dsn-file /etc/boxie/postgres-dsn.secret`.

Migration `0002_command_outbox` preserves pending start/stop commands and removes
obsolete observation commands and dispatcher leases. Its predecessor is undeployed;
incompatible live workflows need a separately reviewed drain or versioned cutover.

Run one migration job before starting updated Boxie processes. API startup does
not migrate. Temporal owns its separate upstream schemas. See
[schema and retention](#boxie-schema-and-retention) for development migrations, cleanup rules,
and artifact reconciliation.

## Preserve data

The installation stores the cluster under the host's Sanctuary state directory. Snapshot the host and verify an off-host database restore before a major PostgreSQL upgrade. Use a fresh cluster and a tested upgrade or dump-and-restore procedure for a major-version change. [Backups and recovery](../../../infra/docs/releases.md#backups-and-recovery)

## Boxie schema and retention

Application tables are mapped SQLModel records. Each operation owns an async
session and transaction; PostgreSQL still enforces constraints, row locks and
advisory locks. Psycopg is the SQLAlchemy driver, with no separate driver pool.
PostgreSQL role/database provisioning and Temporal's upstream schemas are managed
by the Sanctuary infrastructure controller.

For development, review Alembic's generated Python revision before applying it:

```sh
BOXIE_POSTGRES_DSN_FILE=/path/to/development-dsn uv run --package boxie alembic \
  -c packages/boxie/alembic.ini revision --autogenerate -m "Describe schema change"
BOXIE_POSTGRES_DSN_FILE=/path/to/development-dsn uv run --package boxie alembic \
  -c packages/boxie/alembic.ini check
```

Use Alembic schema operations and SQLAlchemy expressions in revisions; do not
introduce SQL strings. Revisions and the environment are packaged in the Boxie
wheel so the explicit upgrade command also works outside the checkout.

## Retention and ownership

Completed sandbox IDs and idempotency keys remain available for **seven days
after confirmed physical cleanup**. After that window a key may be accepted as a
new request. Delivered outbox records remain for seven days after delivery.
`PostgresLifecycle.purge_retained()` removes these records in dependency order.
It never removes pending cleanup, live slots/references, or undelivered commands.
Artifact retirement tombstones remain; a retired UUID cannot be resurrected.

Job IDs, consumer-scoped keys, request hashes and terminal outcomes remain in
`jobs` after lifecycle cleanup and result expiry. The API enforces the seven-day
result window on reads. The retention sweep deletes expired `job_results` bytes
even if lifecycle bookkeeping is still retained. Protect that table and database
backups as consumer output. Once any job is admitted, PostgreSQL refuses to
downgrade past `0007_job_recovery`. The check also protects receipts whose
output and sandbox metadata have expired. Keep the schema when rolling back
application code.

Apply migrations through `0008_job_output_budget`, then upgrade the supervisor
before enabling the job API. The migration accounts for already admitted jobs
at their pinned output limit and for committed results at their stored byte
count. A lower budget blocks new jobs until enough bytes are available.

## Artifact storage and collection

Apply migrations through `0010_artifact_orphan_retry` with the old supervisor stopped,
then start the upgraded supervisor with the same artifact root. On startup it
records expanded file sizes for indexed objects from before the migration. A
missing legacy object retains a conservative 512 MiB charge until collection
or until startup can measure its restored files.
Abandoned directories from before the migration count against installation
capacity until collected. Their consumer identity is unavailable.

The supervisor reserves capacity in PostgreSQL before staging the ZIP. It syncs
complete files under the storage UUID before the transaction that replaces the
staging reservation with the retained object. If publication is interrupted,
PostgreSQL still records either the retained object or its staging reservation.
After the one-hour grace period, `collect_orphans()` can remove abandoned upload
bytes and release the reservation. If deletion fails, the reservation stays
charged. The collector can process other uploads and retry the failed one
after one minute, including after a supervisor restart. The retired artifact
collector waits for sandbox references and releases capacity after deletion
and directory sync.
Run collection on the sole owning supervisor with PostgreSQL available.

To roll back, stop the supervisor and keep the migrated database and artifact
root together. The old supervisor can read the existing artifact metadata and
files. It serves uploads without enforcing quotas. Restarting the upgraded
supervisor inventories retained files and old staging directories again.
