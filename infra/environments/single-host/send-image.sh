#!/usr/bin/env bash
# Emit the loaded image reference after verifying the archive on the host.
set -euo pipefail
config=$1
tag=$2
[[ $tag =~ ^localhost/sanctuary-(boxie|boxie-sandbox|cli-playground|collector):[a-f0-9]{40}$ ]]
id=$(docker image inspect --format '{{.Id}}' "$tag")
[[ $id =~ ^sha256:[a-f0-9]{64}$ ]]
delivery_tag="${tag%:*}:${id#sha256:}"
docker image tag "$id" "$delivery_tag"
archive=$(mktemp)
trap 'rm -f "$archive"' EXIT
docker image save "$delivery_tag" > "$archive"
checksum=$(sha256sum "$archive")
checksum=${checksum%% *}
[[ $checksum =~ ^[a-f0-9]{64}$ ]]
loaded=$(ssh -F "$config" deployment "set -eu
    archive=\$(mktemp)
    trap 'rm -f \"\$archive\"' EXIT
    cat > \"\$archive\"
    echo '$checksum' \"\$archive\" | sha256sum --check --status
    docker image load --input \"\$archive\" >&2
    docker image inspect --format '{{.Id}}' '$delivery_tag'" < "$archive")
[[ $loaded =~ ^sha256:[a-f0-9]{64}$ ]] || { echo 'Invalid loaded image ID' >&2; exit 1; }
if [[ $tag == localhost/sanctuary-boxie-sandbox:* ]]; then
    printf '%s\n' "$loaded"
else
    printf '%s\n' "$delivery_tag"
fi
