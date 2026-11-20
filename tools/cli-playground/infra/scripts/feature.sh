#!/usr/bin/env bash
# Trusted host entry point. Only a feature's own publisher credential reaches its gateway.
set -euo pipefail
umask 077
operation=$1
pr=$2
[[ $pr =~ ^[1-9][0-9]{0,9}$ ]]
owner=/opt/sanctuary/cli-playground
# shellcheck disable=SC1091
source /etc/sanctuary/cli-playground.env
export CLI_PLAYGROUND_DOMAIN
app=playground-pr-$pr
host="https://app-pr-$pr.$CLI_PLAYGROUND_DOMAIN"
case $operation in
    reserve|remove)
        [[ $# == 2 ]]
        python3 "$owner/cli_playground_infra/dokku.py" "$operation" --pr "$pr" >&2
        ;;
    deploy)
        [[ $# == 4 && $3 =~ ^[0-9a-f]{40}$ && $4 =~ ^localhost/sanctuary-playground-pr-[0-9]+:[0-9a-f]{64}$ ]]
        image=$4
        [[ $(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$image") == "$3" ]]
        python3 "$owner/cli_playground_infra/dokku.py" deploy --pr "$pr" --image "$image" >&2
        # stdin holds a representative CLI bundle built from the trusted base revision.
        token=$(cat "/etc/sanctuary/playground-apps/$app/deploy-token")
        response=$(curl --silent --show-error --fail --max-time 120 --max-filesize 16384 \
            --header @<(printf 'Authorization: Bearer %s\n' "$token") --header 'Content-Type: application/zip' \
            --data-binary @- "$host/api/environments?pr=$pr&sha=$3")
        identifier=$(printf 'pull-request:%s' "$pr" | sha256sum | cut -c1-32)
        python3 -c 'import json,sys; sys.exit(json.load(sys.stdin)["id"] != sys.argv[1])' "$identifier" <<< "$response"
        printf '%s/p/%s\n' "$host" "$identifier"
        ;;
    *) exit 2 ;;
esac
