# Compare two SQLite migrations on one private snapshot

A report catalog lets a team reuse the name `weekly` after archiving the old
report. Which proposed index prevents two active reports from taking that
name and keeps the archive readable? Sanctuary could give a release reviewer
the two SQL files and their results side by side. Both would run on copies of
the same staging database on the team's private Boxie host.

A Grafana operator reported that version 10.4.0 failed to start when it
tried to add a unique index to existing user records. Runtime offers
a sandbox recipe for testing migrations on a database copy. SQLite
Rehearsal runs locally and checks rules supplied by the team. Sanctuary
could reuse that checker and test whether sharing the results through
Boxie saves a second maintainer from reconstructing the comparison.
[Grafana upgrade report](https://github.com/grafana/grafana/issues/84118),
[SQLite Rehearsal](https://github.com/KanadeK/sqlite-rehearsal) and
[Runtime's SQLite workflow](https://withruntime.com/integrations/sqlite)

## Try both indexes on the same two reports

Use an empty directory, a POSIX shell, `sqlite3` and SQLite Rehearsal 0.1.0.
In this synthetic example, SQLite writes the archived report to the main
file at a checkpoint. It commits the active report to the write-ahead log
(WAL). The `cp` line deliberately saves the main file alone for comparison.
SQLite's online backup produces the review copy.
[SQLite backup API](https://www.sqlite.org/backup.html) and
[SQLite Rehearsal release](https://github.com/KanadeK/sqlite-rehearsal/releases/tag/v0.1.0)

```sh
sqlite3 -bail catalog.db <<'SQL'
PRAGMA journal_mode=WAL;
CREATE TABLE report (id INTEGER PRIMARY KEY, slug TEXT NOT NULL, archived INTEGER NOT NULL);
INSERT INTO report VALUES (1, 'weekly', 1);
PRAGMA wal_checkpoint(TRUNCATE);
INSERT INTO report VALUES (2, 'weekly', 0);
.shell cp catalog.db main-only.db
.backup review.db
SQL
sqlite3 -bail main-only.db 'PRAGMA integrity_check; SELECT count(*) FROM report;'
sqlite3 -bail review.db 'PRAGMA journal_mode=DELETE;'

printf '%s\n' 'CREATE UNIQUE INDEX report_slug ON report(slug);' > all.sql
printf '%s\n' 'CREATE UNIQUE INDEX report_slug ON report(slug) WHERE archived = 0;' > active.sql
cat > history.sql <<'SQL'
VALUES (1, 1), (2, 0)
EXCEPT SELECT id, archived FROM report WHERE slug = 'weekly';
SQL
```

The history check returns any expected pair of report ID and archive status
missing after the migration. Run each command separately. Each starts from
`review.db` and tests its index on a fresh copy.

```sh
sqlite-rehearsal run review.db --up all.sql --check history.sql
sqlite-rehearsal run review.db --up active.sql --check history.sql
```

| Migration on the review copy | Observed result |
| --- | --- |
| Index every report | Exit 1. Creating the index failed because both rows have the same name. |
| Index active reports | Exit 0. Both original rows survived. A separate write test rejected a second active `weekly` and accepted another archived one. |
| Control that discarded the archive before indexing every report | Exit 1. The migration and SQLite's integrity checks passed. The history check found the missing report. |

The query on `main-only.db` printed `ok` and `1`. SQLite found a healthy
database with just the archived row, so it could create the whole-table
index there. The online backup included both rows. It also retained WAL
mode. When that file arrived alone on Boxie's read-only artifact mount,
the checker could not create the WAL files beside it. Setting
`journal_mode=DELETE` on `review.db` before packaging let the checker read
both rows. Testing write contention would require the application's usual
journal mode and concurrent writers.
[SQLite on read-only media](https://www.sqlite.org/wal.html#read_only_databases)

## What the reviewer would receive

The team's release service would upload one ZIP containing the snapshot,
both SQL files and the history check to its private Boxie host. It would
submit two jobs against that upload under one versioned profile with a
pinned image containing the application's SQLite build and SQLite
Rehearsal. Each approved command would select one SQL file, set
`TMPDIR=/workspace` for the checker's scratch copy and return the stages
from its JSON report on stdout. Start with staging databases under 4 MiB
to leave room for the copy, journal and index in the default 64 MiB workspace.
[Boxie job API](../../packages/boxie/docs/consumer-api.md#submit-a-job-and-retrieve-its-result)
and [workspace limits](../../packages/boxie/docs/execution.md#isolation-and-lifetime)

In a Docker Desktop trial using Boxie's ZIP extraction, job settings and
output capture with `runc`, the unreadable WAL backup and the rejected
index both exited 1. Their reports identified the failure at `snapshot` and
`forward_migration`, respectively. The review page would match the SHA-256
digests of the database, SQL and check to the submitted files before
showing a verdict. It would mark the comparison incomplete if either
report was missing or truncated, a digest differed, or the checker could
not open the snapshot.

## Would a team use this for its next release?

Recruit two teams that already run Boxie on private Linux hosts with
gVisor. Ask a maintainer and reviewer at each to try two matched sets of
migrations, including a duplicate name, a lost archive and an incomplete
report. Use the proposed page for one set. For the other, share SQLite
Rehearsal's JSON reports through the team's usual review or CI system.
Reverse the order for the second team.

Count hands-on minutes from preparing the snapshot to the second person
identifying which SQL preserves the archive. Package the integration if
both pairs choose the correct migration, identify every incomplete result
and save enough time at their normal review frequency to cover setup and
upkeep within a quarter.
