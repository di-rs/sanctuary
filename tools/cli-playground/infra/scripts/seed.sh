#!/usr/bin/env bash
# Create a representative terminal bundle with command metadata using the trusted echor binary.
set -euo pipefail
sha=$1 binary=$2 destination=$3
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
SANCTUARY_CLI_SCHEMA=1 "$binary" --help > "$temporary/schema.json"
digest=$(sha256sum "$binary" | cut -d' ' -f1)
jq -n --arg sha "$sha" --arg base "$(git rev-parse HEAD)" --arg digest "$digest" --slurpfile schema "$temporary/schema.json" \
    '{schema_version:1, head_sha:$sha, base_sha:$base, clis:[{name:"echor",binary_sha256:$digest,head:$schema[0],base:$schema[0],comparison:"available"}]}' > "$temporary/catalog.json"
zip -jq "$destination" "$binary" "$temporary/catalog.json"
