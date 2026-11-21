#!/bin/bash
set -euo pipefail
umask 077
state=${SANCTUARY_STATE:-/var/lib/sanctuary}
site=${SANCTUARY_SITE:-sanctuary}
stage=$(mktemp -d "$state/.backup.XXXXXXXX")
trap 'rm -f "$stage/database.age" "$stage/backup.prom"; rmdir "$stage"' EXIT
# Only ciphertext is written to disk. The object appears after the dump and encryption succeed.
docker exec -i "$site-postgres-db-1" pg_dumpall -U postgres --clean --if-exists \
    | gzip -1 | age -r "${BACKUP_RECIPIENT:?}" > "$stage/database.age"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
AWS_ACCESS_KEY_ID="${BACKUP_KEY_ID:?}" AWS_SECRET_ACCESS_KEY="${BACKUP_SECRET:?}" \
    aws --region auto --endpoint-url "https://${CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com" \
    s3 cp --only-show-errors "$stage/database.age" "s3://${BACKUP_BUCKET:?}/postgres/$stamp.sql.gz.age"
printf 'sanctuary_backup_timestamp_seconds %s\n' "$(date +%s)" > "$stage/backup.prom"
chmod 644 "$stage/backup.prom"
mv "$stage/backup.prom" "$state/metrics/backup.prom"
