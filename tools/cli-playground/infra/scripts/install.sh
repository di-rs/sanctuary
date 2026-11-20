#!/usr/bin/env bash
# Bootstrap the platform once. Dokku clones the credential-free template for each PR.
set -euo pipefail
umask 077
owner=${SANCTUARY_CLI_PLAYGROUND_DIR:-/opt/sanctuary/cli-playground}
config=${SANCTUARY_CONFIG_DIR:-/etc/sanctuary}
# shellcheck disable=SC1091
source "$config/settings.env"
dokku() { docker exec sanctuary-dokku dokku "$@"; }

install -d -m 0700 "$config/cli-playground" "$config/playground-apps"
token=$config/cli-playground/preview-token
if [[ ! -e $token && ! -L $token ]]; then openssl rand -hex 32 > "$token"; fi
[[ ! -L $token && -f $token && -s $token && -n $(find "$token" -perm 0600) ]] || {
    echo 'Expected a private, nonempty preview credential.' >&2; exit 1
}
[[ $(docker network inspect --format '{{.Internal}}' playground-apps) == true ]]
docker volume create cli-playground-certificates >/dev/null
docker compose --env-file "$config/settings.env" -f "$owner/compose.production.yml" up -d --build --remove-orphans --wait
dokku nginx:set --global client-max-body-size 512m
dokku nginx:set --global proxy-read-timeout 3600s
for app in cli-playground playground-review-template; do
    dokku apps:exists "$app" || dokku apps:create "$app"
    dokku network:set "$app" initial-network playground-apps
    dokku ports:set "$app" http:80:8000
    dokku checks:disable "$app" web
    dokku config:set --no-restart "$app" POSTGRES_DATABASE_SCHEME=postgresql+psycopg \
        CLI_PLAYGROUND_DATA_DIR=/var/lib/cli-playground CLI_PLAYGROUND_BOXIE_URL=http://boxie-api:8090 \
        CLI_PLAYGROUND_BOXIE_CREDENTIAL_FILE=/run/secrets/consumer
    dokku docker-options:add "$app" deploy,run --read-only --cap-drop=ALL --security-opt=no-new-privileges --tmpfs=/tmp:rw,nosuid,size=48m
done
# Boxie owns this reserved bridge address across independent releases.
dokku config:set --no-restart playground-review-template CLI_PLAYGROUND_BOXIE_URL=http://10.237.93.2:8090
dokku docker-options:add playground-review-template deploy,run --runtime=runsc --user=65532:65532 \
    --memory=384m --cpus=0.75 --pids-limit=128 --tmpfs=/var/lib/cli-playground:rw,nosuid,noexec,size=96m,uid=65532
dokku domains:set cli-playground "$CLI_PLAYGROUND_DOMAIN" "*.$CLI_PLAYGROUND_DOMAIN"
dokku config:set --no-restart cli-playground "CLI_PLAYGROUND_PUBLIC_URL=https://$CLI_PLAYGROUND_DOMAIN" \
    "CLI_PLAYGROUND_PREVIEW_DOMAIN=$CLI_PLAYGROUND_DOMAIN"
dokku docker-options:add cli-playground deploy,run --volume=cli-playground-data:/var/lib/cli-playground \
    "--volume=$config/boxie/consumer.secret:/run/secrets/consumer:ro" \
    "--volume=$config/cli-playground/preview-token:/run/secrets/CLI_PLAYGROUND_DEPLOY_TOKEN:ro" \
    --log-driver=journald --log-opt=mode=non-blocking --log-opt=max-buffer-size=4m --log-opt=tag=cli-playground-api
dokku postgres:exists cli-playground || dokku postgres:create cli-playground >/dev/null
dokku postgres:linked cli-playground cli-playground || dokku postgres:link cli-playground cli-playground --no-restart --env-var CLI_PLAYGROUND_DATABASE_URL >/dev/null
