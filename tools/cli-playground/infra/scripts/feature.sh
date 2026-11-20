#!/usr/bin/env bash
# Manage one review app on the Dokku host. stdin is the image for deploy, or the seed ZIP for publish.
set -euo pipefail
umask 077
operation=$1 pr=$2
[[ $pr =~ ^[1-9][0-9]{0,9}$ ]]
# shellcheck disable=SC1091
source /etc/sanctuary/settings.env
app=playground-pr-$pr
host="https://app-pr-$pr.$CLI_PLAYGROUND_DOMAIN"
root=/etc/sanctuary/playground-apps
dir=$root/$app
grants=/etc/sanctuary/consumer-grants
repository=localhost/sanctuary-$app
dokku() { docker exec -i sanctuary-dokku dokku "$@"; }
digest() { printf %s "$1" | sha256sum | cut -d' ' -f1; }
clean_images() {
    local tag
    while IFS= read -r tag; do
        if [[ $tag != "${1:-}" ]]; then docker image rm "$repository:$tag" >&2; fi
    done < <(docker image ls "$repository" --format '{{.Tag}}')
}
exec 9>"/run/sanctuary-$app.lock"
flock 9
case $operation in
    deploy)
        sha=$3
        [[ $sha =~ ^[0-9a-f]{40}$ ]]
        (
            flock 8
            limit=3
            if [[ -f $root/limit ]]; then read -r limit < "$root/limit"; fi
            [[ $limit =~ ^[0-9]+$ ]]
            if [[ ! -d $dir ]] && (( $(find "$root" -maxdepth 1 -type d -name 'playground-pr-*' | wc -l) >= limit )); then
                echo "All $limit Playground preview slots are in use" >&2; exit 1
            fi
            mkdir -p "$dir"
        ) 8>"$root/.capacity"
        if [[ ! -s $dir/consumer ]]; then printf 'scoped.%s' "$(openssl rand -hex 32)" > "$dir/consumer"; fi
        if [[ ! -s $dir/publisher ]]; then openssl rand -hex 32 > "$dir/publisher"; fi
        chown 65532:65532 "$dir/consumer" "$dir/publisher"
        grant="$grants/$(digest "$(<"$dir/consumer")")"
        if [[ ! -s $grant ]]; then printf '%s\n' "$app" > "$grant"; fi
        dokku apps:clone --skip-deploy --ignore-existing playground-review-template "$app" </dev/null
        dokku checks:disable "$app" web </dev/null
        dokku domains:set "$app" "${host#https://}" </dev/null
        dokku config:set --no-restart "$app" "CLI_PLAYGROUND_PUBLIC_URL=$host" </dev/null
        dokku docker-options:add "$app" deploy,run "--volume=$dir/consumer:/run/secrets/consumer:ro" \
            "--volume=$dir/publisher:/run/secrets/CLI_PLAYGROUND_DEPLOY_TOKEN:ro" </dev/null
        dokku postgres:exists "$app" </dev/null || dokku postgres:create "$app" --memory 320 \
            --shm-size 160m --custom-env PGDATA=/dev/shm/pgdata </dev/null >/dev/null
        dokku postgres:linked "$app" "$app" </dev/null || dokku postgres:link "$app" "$app" \
            --no-restart --env-var CLI_PLAYGROUND_DATABASE_URL </dev/null >/dev/null
        # libpq accepts a numeric peer while retaining the plugin's private user and database.
        link="dokku.postgres.$app.$app"
        db_ip=$(docker inspect --format "{{(index .NetworkSettings.Networks \"$link\").IPAddress}}" "dokku.postgres.$app")
        [[ $db_ip =~ ^[0-9]+(\.[0-9]+){3}$ ]]
        dokku config:set --no-restart "$app" "PGHOSTADDR=$db_ip" </dev/null
        bash "$(dirname "$0")/deploy-image.sh" "$app" "$repository:$sha" git:load-image
        clean_images "$sha"
        ;;
    publish)
        sha=$3
        [[ $sha =~ ^[0-9a-f]{40}$ ]]
        identifier=$(digest "pull-request:$pr"); identifier=${identifier:0:32}
        curl -fsS --retry 45 --retry-all-errors --retry-delay 2 --max-time 5 "$host/healthz" >/dev/null
        if ! curl -fs --max-time 10 --max-filesize 16384 "$host/api/environments/$identifier" | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(d["sha"]!=sys.argv[1] or not d["revision"])' "$sha" 2>/dev/null; then
            curl -fsS --max-time 120 --max-filesize 16384 --header @<(printf 'Authorization: Bearer %s\n' "$(<"$dir/publisher")") \
                --header 'Content-Type: application/zip' --data-binary @- "$host/api/environments?pr=$pr&sha=$sha" \
                | python3 -c 'import json,sys; sys.exit(json.load(sys.stdin)["id"]!=sys.argv[1])' "$identifier"
        fi
        printf '%s/p/%s\n' "$host" "$identifier"
        ;;
    remove)
        if [[ -s $dir/consumer ]]; then rm -f "$grants/$(digest "$(<"$dir/consumer")")"; fi
        if dokku apps:exists "$app"; then dokku apps:destroy "$app" --force; fi
        # Dokku removes the app's nginx.conf after its post-delete hooks have run.
        dokku nginx:reload
        if dokku postgres:exists "$app"; then dokku postgres:destroy "$app" --force; fi
        if [[ -s $dir/consumer ]]; then
            token="scoped.$(openssl rand -hex 32)"; grant="$grants/$(digest "$token")"
            trap 'rm -f "$grant"' EXIT
            printf '%s\n' "$app" > "$grant"
            api=$(docker ps -q --filter label=com.docker.compose.service=api --filter network=boxie-consumers)
            printf '%s\n' "$token" | docker exec -i "$api" python -m boxie.bootstrap.retire_consumer "$app"
        fi
        clean_images
        rm -rf -- "$dir"
        ;;
    *) exit 2 ;;
esac
