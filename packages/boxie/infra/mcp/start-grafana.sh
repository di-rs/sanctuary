#!/bin/sh
set -eu
GRAFANA_SERVICE_ACCOUNT_TOKEN=$(cat /run/secrets/grafana-token)
export GRAFANA_SERVICE_ACCOUNT_TOKEN
exec /app/mcp-grafana --transport stdio --disable-write --usage-stats disabled \
    --enabled-tools search,datasource,dashboard,prometheus
