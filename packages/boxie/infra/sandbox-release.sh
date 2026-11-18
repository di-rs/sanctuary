#!/usr/bin/env bash
# Change the approved sandbox profile and reload only its supervisor.
set -euo pipefail
[[ $# == 1 && $1 =~ ^[a-z0-9][a-z0-9./:_-]+@sha256:[a-f0-9]{64}$ ]] || exit 2
image=$1
config=${SANCTUARY_CONFIG_DIR:-/etc/sanctuary}
boxie=${SANCTUARY_BOXIE_DIR:-/opt/sanctuary/boxie}
docker pull "$image"
BOXIE_SANDBOX_IMAGE=$image python3 "$boxie/boxie_infra/installation.py" "$boxie" --profile-only
compose() {
    docker compose --env-file "$config/boxie.env" --env-file "$config/boxie-image.env" \
        -f "$boxie/compose.production.yml" -f "$boxie/compose.observability.yml" "$@"
}
compose stop --timeout 60 supervisor
compose up -d --no-build --pull never --no-deps --force-recreate --wait --wait-timeout 150 supervisor
compose exec -T api python - sandbox <"$boxie/boxie_infra/readiness.py"
