# Back up and restore Boxie off host

Use this procedure to recover Boxie and its Temporal instance on an isolated
replacement host. Each recovery point begins after all accepted work drains.
Keep the replacement isolated from consumers until the former owner is fenced
and you have reconciled requests made after the recovery point.

The encrypted recovery archive contains the Boxie, Temporal persistence and
Temporal visibility databases, Boxie artifact bytes, the supervisor journal
when present, installation and host IDs, credentials, configuration and the
Temporal certificate set. Its manifest records the source revision, PostgreSQL
and Temporal image digests, schema versions and UTC recovery point. Disposable
sandbox disks, processes and terminal sessions are lost when the host fails.
Observability logs follow their own retention policy. Republish playground
previews from their source revisions, or protect the gateway separately if it
is part of your recovery target. [Playground recovery](../../tools/cli-playground/docs/database.md#back-up-and-restore)

## Prepare the backup service

1. Choose an acceptable loss interval and elapsed recovery target.
   Choose a maintenance window that accommodates draining, and size private,
   encrypted scratch space for the archive and database dumps. Use Python 3.12
   or later and restic with `--stdin-from-command` support.
2. Initialize a dedicated restic repository on a separate host or account.
   Use TLS and an append-only rest-server endpoint for the backup writer, with
   separate credentials for recovery and retention. Set `RESTIC_REPOSITORY` and
   `RESTIC_PASSWORD_FILE` in the private scheduler environment. Keep the
   repository access credentials, encryption password, Pulumi state-backend
   passphrase and ingress enrollment credentials in independent operator
   escrow. The archive contains consumer outputs and signing keys. Restrict
   repository reads and decrypted staging to recovery operators.
3. Configure a Healthchecks-compatible monitor away from the Boxie host.
   Store the per-check HTTPS ping URL in a mode-0600 file. Route failure and
   missed-run alerts to the operator. Choose the backup interval, monitor grace
   and maximum age of a capture at publication so their sum fits the loss interval.
   The success ping body records the verified snapshot ID, archive SHA-256,
   recovery point and verification time. Preserve receipts off host so an
   operator can select a known recovery point after host loss.
4. Set retention from the repository administration side. Review successful
   receipts and the deletion list before forgetting snapshots. With a dedicated
   repository, review `restic forget --dry-run --keep-within "$RETENTION"`, then
   apply the selected policy and prune. Use a time-based window chosen by the
   operator and preserve a verified point through maintenance. Schedule
   `restic check --read-data` with repository administration credentials.
   [restic retention and append-only repositories](https://restic.readthedocs.io/en/stable/060_forget.html)

## Capture and publish a recovery point

Run the operator commands from a trusted checkout at the reviewed recovery-tool
revision. The examples use the shared-host data paths. Set `POSTGRES_CONTAINER`
and `TEMPORAL_CONTAINER` to the exact container IDs for the selected installation,
`DEPLOYED_REVISION` to its 40-character source revision and `BACKUP_MAX_AGE_SECONDS`
to the configured publication limit. Use a dedicated directory with mode 0700
for `WORK` and set `BACKUP_PING_FILE` to the private monitor URL file.

1. Close consumer ingress and all direct admission paths. Leave workers running
   until accepted jobs are terminal, their output accounting and physical
   cleanup have settled, and terminal sandboxes are closed. Serialize the
   maintenance window with releases, schema operations and configuration
   updates. Stop Boxie API, supervisor and Temporal server in that order. Keep
   PostgreSQL running and keep other clients of these databases stopped.
2. Capture the installation. This takes the supervisor's existing local lock,
   checks installed Docker resources, database clients, job and sandbox
   accounting, artifact availability and journal identity, then dumps all
   three databases while writers are stopped. A nonzero exit means the
   operator must resolve the reported condition before using a new capture.

   ```sh
   recovery=packages/boxie/infra/boxie_infra/recovery.py
   python3 "$recovery" capture \
     --postgres "$POSTGRES_CONTAINER" --temporal "$TEMPORAL_CONTAINER" \
     --revision "$DEPLOYED_REVISION" --config /etc/sanctuary \
     --data /srv/sanctuary/boxie --output "$WORK/capture"
   ```

3. Resume the source after capture, starting Temporal first and verifying Boxie
   readiness before admitting consumers. Publish the private staging archive.
   Publication reads the encrypted snapshot back from the repository and
   compares its bytes to the capture before it sends a success ping.

   ```sh
   python3 "$recovery" publish --capture "$WORK/capture" \
     --installation "$(cat /etc/sanctuary/boxie/installation-id)" \
     --max-age-seconds "$BACKUP_MAX_AGE_SECONDS" --ping-file "$BACKUP_PING_FILE"
   ```

4. Run the sequence on the operator's scheduler. Propagate nonzero exits from
   every stage, including quiescing and resuming services. Route every failed
   run through the following command. Have the scheduler clean up decrypted
   staging and alert on failure to restart the source. The off-host monitor
   also alerts when runs stop reaching it.

   ```sh
   python3 "$recovery" report-failure --ping-file "$BACKUP_PING_FILE"
   ```

Record time spent draining, time with writers stopped and time to verified
publication. If drained maintenance cannot meet the required interval, keep the
recovery gate open until the operator has a capture method that meets it.

## Restore to an isolated host

1. Fence the former owner before enabling a replacement with the same identity.
   Verify power-off or destroy its ability to run workloads and reach storage,
   Temporal and ingress. A file lock applies only on one host. Preserve the old
   volume or disk separately if reachable. Keep production traffic, playground
   republishing and automatic client retries disabled while recovering.
2. Retrieve a success receipt from the off-host record using separate recovery
   credentials. Start the recovery timer at declaration of host loss. Download
   and verify the selected snapshot into a new private directory.

   ```sh
   recovery=packages/boxie/infra/boxie_infra/recovery.py
   python3 "$recovery" receive --receipt "$RECEIPT" --output "$WORK/restore"
   ```

3. Use the manifest's source revision and digest-pinned images for restoration.
   Use the [PostgreSQL initialization procedure](../../packages/boxie/docs/database.md#start-a-fresh-database)
   with a newly named data volume and the recovered database credentials. Start
   only PostgreSQL. The initializer creates the three owners, databases and
   grants. Keep the recovered source volume selector as evidence and write a
   replacement selector for the new volume before running host setup. Restore
   into the empty databases without running schema setup or Alembic first.

   ```sh
   python3 "$recovery" restore-databases --capture "$WORK/restore" \
     --postgres "$NEW_POSTGRES_CONTAINER"
   ```

   Each database import is transactional. If any import or verification fails,
   discard the disposable target cluster and retry with a fresh target.
   Compare database owners and role access, and verify stored schema versions
   before any version upgrade. Rehearse upgrades separately. [PostgreSQL data preservation](../../packages/boxie/docs/database.md#preserve-data)

4. Install the recovered configuration, artifacts and journal at the fresh
   host's deployment paths. Check executable bits, secret file modes and
   numeric owners against the [certificate installer](../../packages/boxie/infra/certificates.sh)
   and [Boxie deployment contract](../../packages/boxie/docs/deployment.md#deployment-prerequisites).
   The receive command stages data with the recovery user's ownership.
   Reinstate TLS and ingress credentials from escrow as required. Start
   Temporal privately and verify the namespace and a known workflow run,
   result and visibility record before starting Boxie in isolation.
5. Compare source receipts and any independently retained consumer/client
   records with the restored job table. A request accepted after the backup may
   have changed an external system even when the recovered API has no job
   receipt. Record those requests as unresolved until the operator and consumer
   owner reconcile external effects. For clients with incomplete receipts, keep
   admission paused until they can reconcile their exposure. Any repeat job
   requires an explicit new submission after reconciliation. [Job recovery](../../packages/boxie/docs/execution.md#noninteractive-job-recovery)
6. Verify an owned artifact's stored digest and payload, deny a foreign owner,
   retrieve a retained job result, and run one new sandbox job through result,
   Docker removal, slot release and artifact reference cleanup. Check the new
   result's reservation equals its actual byte count. Only then open the
   permitted consumer routes and record elapsed time and observed loss.

## Record the drill

On an authorized disposable host, deliberately fail a capture or upload and
confirm the failure notification arrives. Suppress the next scheduled run and
confirm the missed-run alert. Record the recovery point in UTC, loss since that
point, minutes to service, PostgreSQL and Temporal versions, verified job and
workflow outcomes and both alert results. Include evidence of former-owner
fencing. Compare the timings with the agreed targets.

The production gate also requires the operator to identify needed data in the
retained PostgreSQL 17 volume and rehearse any migration on separate storage.
The same-host minor-version rollback rehearsal covers image compatibility and
volume preservation. [Recovery issue](https://github.com/di-rs/sanctuary/issues/38) · [PostgreSQL 18.7 rehearsal](https://github.com/di-rs/sanctuary/pull/311)
