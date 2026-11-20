#!/usr/bin/env bash
set -euo pipefail
[[ $# == 0 ]] || exit 2
owner=${SANCTUARY_CLI_PLAYGROUND_DIR:-/opt/sanctuary/cli-playground}
config=${SANCTUARY_CONFIG_DIR:-/etc/sanctuary}
if ! docker network inspect cli-playground-proxy >/dev/null 2>&1; then docker network create cli-playground-proxy >/dev/null; fi
for volume in cli-playground-data cli-playground-certificates; do
    if ! docker volume inspect "$volume" >/dev/null 2>&1; then docker volume create "$volume" >/dev/null; fi
done
if ! docker network inspect playground-apps >/dev/null 2>&1; then
    docker network create --internal playground-apps >/dev/null
fi
[[ $(docker network inspect --format '{{.Internal}}' playground-apps) == true ]]
docker compose --env-file "$config/cli-playground.env" -f "$owner/compose.production.yml" \
    up -d --wait --wait-timeout 300 dokku proxy
