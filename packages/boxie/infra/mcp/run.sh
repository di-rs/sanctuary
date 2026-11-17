#!/bin/sh
# stdout belongs exclusively to the MCP protocol.
set -eu
case "${1:-}" in
    grafana|temporal) adapter=$1 ;;
    *) echo 'Usage: sanctuary-mcp grafana|temporal' >&2; exit 2 ;;
esac
[ "$#" -eq 1 ] || exit 2
exec docker compose --env-file /etc/sanctuary/boxie.env \
    -f /opt/sanctuary/boxie/mcp/compose.yml \
    run --rm --no-deps -T "$adapter"
