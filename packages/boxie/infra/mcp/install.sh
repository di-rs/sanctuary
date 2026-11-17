#!/usr/bin/env bash
set -euo pipefail
owner=${SANCTUARY_BOXIE_DIR:-/opt/sanctuary/boxie}
for network in boxie-control boxie-grafana-origin; do
    [[ $(docker network inspect --format '{{.Internal}}' "$network") == true ]]
done
install -d -o 472 -g 0 -m 0700 /etc/sanctuary/mcp
mcp() { timeout 180 docker compose --env-file /etc/sanctuary/boxie.env -f "$owner/mcp/compose.yml" "$@"; }
mcp pull grafana temporal
mcp run --rm --no-deps -T grafana-bootstrap
install -m 0755 "$owner/mcp/run.sh" /usr/local/bin/sanctuary-mcp
