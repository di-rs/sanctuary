#!/bin/sh
set -eu
for kind in temporal visibility; do
    database=temporal
    if [ "$kind" = visibility ]; then database=temporal_visibility; fi
    # The Temporal schema tool preserves an already-upgraded version.
    SQL_PASSWORD="$POSTGRES_PWD" temporal-sql-tool --plugin postgres12 --ep sanctuary-postgres --port 5432 --user "$POSTGRES_USER" --db "$database" setup-schema -v 0.0
    SQL_PASSWORD="$POSTGRES_PWD" temporal-sql-tool --plugin postgres12 --ep sanctuary-postgres --port 5432 --user "$POSTGRES_USER" --db "$database" update-schema -d "/etc/temporal/schema/postgresql/v12/$kind/versioned"
done
