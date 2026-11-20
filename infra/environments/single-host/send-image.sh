#!/usr/bin/env bash
# Emit the loaded image reference only after the host verifies the local image ID.
set -euo pipefail
config=$1
tag=$2
[[ $tag =~ ^localhost/sanctuary-(boxie|boxie-sandbox|cli-playground|collector):[a-f0-9]{40}$ ]]
id=$(docker image inspect --format '{{.Id}}' "$tag")
[[ $id =~ ^sha256:[a-f0-9]{64}$ ]]
delivery_tag="${tag%:*}:${id#sha256:}"
docker image tag "$id" "$delivery_tag"
docker image save "$delivery_tag" | ssh -F "$config" deployment 'docker image load' >&2
loaded=$(ssh -F "$config" deployment "docker image inspect --format '{{.Id}}' '$delivery_tag'")
[[ $loaded == "$id" ]]
if [[ $tag == localhost/sanctuary-boxie-sandbox:* ]]; then
    printf '%s\n' "$id"
else
    printf '%s\n' "$delivery_tag"
fi
