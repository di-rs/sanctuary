# Release operations

Run production actions from the protected `master` branch in the GitHub Actions tab. Each action writes one desired revision to private R2. The host applies projects in dependency order, runs required schema jobs and records successful applications locally. A failed migration leaves the new revision pending for retry.

| Change | GitHub workflow |
| --- | --- |
| Production website and released CLI bundle | **Deploy Playground** |
| Boxie API, supervisor and sandbox image | **Deploy Boxie** |
| PostgreSQL, Temporal, observability or edge | **Deploy Sanctuary services**, then select the component |
| Issue, rotate or revoke a gateway credential | **Manage Playground service keys** |

For a rollback, select the same component and enter the full 40-character commit of a previously published release in **rollback**. Leave it empty to build the selected protected commit. Schema changes survive an image rollback. Confirm that the older binary can read the new schema before choosing a rollback, especially across PostgreSQL major versions.

## PR previews

An open, ready PR from a branch in this repository gets a preview when its complete merge-base diff touches a CLI, its shared utilities, or workspace build inputs. The default-branch workflow reconciles PR events and checks all open PRs every six hours. Drafting or closing a PR, or reverting its last CLI change, requests removal. The host revokes the key, removes the public route, drains Boxie resources and removes that preview's database. Preview keys expire after 24 hours if the publisher stops renewing them.

Open **Sanctuary / Playground** on the PR commit for the verified preview URL. The status appears after the public gateway serves that commit. The Actions run summary also contains the expected address. A PR with a failing build can keep serving its prior working revision until the existing lease expires. Production code and each preview have independent configuration and database identities. [Command catalogs](../../tools/cli-playground/docs/previews.md)

## Service keys

Enter `playground` for production or `pr-42` for a preview in **Manage Playground service keys**. **rotate** gives the existing deployment a fresh key and retires its predecessor. **revoke** blocks new Boxie authorizations. **issue** enables a revoked deployment again. Gateways read their protected credential file on new requests. Rotation and revocation take effect when the host applies the request. Previously authorized open connections follow the service's normal connection and sandbox lifetime.

## Backups and recovery

At 03:15 UTC the backup timer runs a logical dump of PostgreSQL roles and all databases, compresses it, encrypts it with `age` and uploads the ciphertext to the private backup bucket under `postgres/`. A successful upload updates the backup timestamp metric. Choose a retention policy for that bucket. The decryption identity belongs to the operator.

For a database restore drill, initialize an empty, isolated cluster on the same PostgreSQL major. Give its bootstrap superuser a name absent from the source cluster, such as `recovery_admin`. This account stays connected while the dump recreates the original roles. Download the encrypted backup from R2. In the recovery host's console, use the off-host key and your container name to stream the dump into the new cluster.

```sh
set -o pipefail
age --decrypt --identity /secure/backup-identity backup.sql.gz.age \
  | gzip -dc | docker exec -i recovery-postgres-db-1 \
    psql -X -v ON_ERROR_STOP=1 -U recovery_admin -d postgres
```

Review the restore output, verify database owners and row counts, and exercise a Temporal workflow and a fresh Playground session before directing traffic there. The SQL dump covers database state. Boxie artifact files, TLS keys, host credentials and active terminal files live on the host filesystem. Full recovery of existing sessions requires a separate matching host snapshot and the off-host decryption key. For an empty installation, publish the protected services and CLI bundles to a fresh state directory instead.

The Hetzner console also provides emergency diagnostics. `systemctl status sanctuary-sync.timer sanctuary-backup.timer` shows scheduling. `journalctl -u sanctuary-sync -u sanctuary-backup` identifies the component awaiting a successful operation. The host keeps its applied release records under `/var/lib/sanctuary/applied`.
