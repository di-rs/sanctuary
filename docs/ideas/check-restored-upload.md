# Check that a restored Boxie host can read an earlier upload

A private Boxie host can return yesterday's successful checksum after a
restore even when the file it checked is gone. Boxie stores job results in
PostgreSQL and extracted uploads on the supervisor's disk. Sanctuary could
give operators a check that runs a new job against a known upload and adds
its verdict to the team's restore report.
[How Boxie stores results and artifacts](../../packages/boxie/docs/database.md#retention-and-ownership)

A GitLab 12.2.5 operator reported that a restore completed without errors but
put files under the wrong paths, leaving CI artifacts unavailable. GitLab's
integrity checks compare locally stored uploads with their recorded checksums.
Veeam SureBackup lets a team supply its own script to test a restored VM.
Teams using it could call the Boxie check from that script.
[GitLab operator report](https://gitlab.com/gitlab-org/gitlab/-/issues/35850),
[GitLab file checks](https://docs.gitlab.com/administration/raketasks/check/#uploaded-files-integrity)
and [SureBackup application tests](https://helpcenter.veeam.com/docs/vbr/userguide/surebackup_job_tests_hv.html)

## Give each backup a known input

For a staging drill, choose a different marker for each recovery point.
To prepare the sample for backup 18, run the following in an empty directory
with `zip` and `sha256sum` installed.

```sh
printf 'batch-18\n' > probe.txt
zip -q probe.zip probe.txt
sha256sum probe.zip probe.txt
```

Use the ZIP's digest for the upload. Keep the file's digest as the expected
answer. Give a dedicated consumer a job profile that permits
`/usr/bin/sha256sum /opt/artifact/probe.txt`. Run it once, confirm the
expected answer and wait for cleanup. Take the staging backup with the
artifact still active. Keep its artifact ID, the completed job ID and the
file digest alongside the backup set's ID outside the host.
[Boxie job submission and results](../../packages/boxie/docs/consumer-api.md#submit-a-job-and-retrieve-its-result)

Confirm the selected backup ID in the restore tool. A later backup can also
contain an earlier marker. Bring up the copy on an isolated host with its
own Docker daemon, databases and Temporal service. Connect to its private
Boxie API as the consumer that created the marker.

1. Look up the saved job with `GET /v1/jobs/{id}` and confirm it succeeded.
   On HTTP 404, stop and check the backup ID and consumer identity. The job's
   state remains readable after its output expires seven days after cleanup.
2. Save a fresh submission key and send `POST /v1/jobs` with the **existing
   artifact ID**, the granted profile and the same checksum command. Reuse
   that key if the reply is lost. Confirm the returned job ID differs from
   the one saved before backup.
3. Report **Marker verified** when the new job succeeds and its result has
   exit code zero, `truncated` set to `false` and the expected full checksum
   line in decoded stdout. Record both job IDs, the backup ID and the
   observed digest. A timeout leaves the check incomplete.

## What the restored jobs saw

A local trial used `pg_dump` and `pg_restore` on Boxie's PostgreSQL 17
database and copied the corresponding artifact directories while the
application was stopped. Every restored copy returned HTTP 200 from
`/readyz`. The client compared full SHA-256 digests. The table shows the
first 12 digits.

| Restored copy | Saved result for backup 18 | New job reading the existing upload |
| --- | --- | --- |
| Backup 18 intact | Expected digest | Exited 0 with `4bec69b09b71`, the expected digest. |
| File missing from its directory | Expected digest | Exited 1 because it could not open the file. |
| Backup 17's nine bytes at backup 18's path | Expected digest | Exited 0 with `4b78688e02b3`, the digest for backup 17. |
| Backup 17's database and files | HTTP 404 for the requested job | Stopped at lookup. Backup 17's own job was readable. |
| Backup 18 intact, with the cleanup time aged eight days | Job succeeded. Output expired (HTTP 410). | Exited 0 with the expected digest. |

On the copies with missing or substituted bytes, retrying the original job
request returned the old job ID and its successful state. Uploading the
identical ZIP under the same artifact ID also returned HTTP 200. Boxie
acknowledges the matching database record and discards the retry's temporary
files.
[Boxie artifact publication](../../packages/boxie/src/boxie/persistence/postgres_artifacts.py)

The trial used Docker Desktop's `runc` and a fresh Temporal test server for
each restore. Even the intact copy passed with the old workflow absent from
Temporal. The result covers one upload. Boxie's full recovery rehearsal also
requires restored Temporal persistence and visibility databases, workflow
execution and application accounting.
[Production recovery requirements](../../packages/boxie/docs/database.md#recovery-prerequisite-for-production-activation)

## Would operators keep the check?

Give two operators matched staging backups on native Linux with gVisor.
Have each classify the copies using their usual restore checks and the
proposed check, reversing the order for the second operator. Include any
custom validation they already run. Record decisions before revealing each
condition and count hands-on minutes, including marker preparation. Package
the check if both operators classify every copy correctly and at least one
chooses it for the next scheduled rehearsal because it caught a bad restore
their usual checks accepted or reduced their hands-on time.
