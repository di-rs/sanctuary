#!/bin/bash
# The candidate is data to the disposable builder. Never mount the runner's
# command files, credentials, caches, Docker socket, or the control checkout.
set -euo pipefail
trusted=$1
candidate=$2
base=$3
head=$4
destination=$5
docker build --platform linux/amd64 --quiet --file "$trusted/infra/images/Bundle.Dockerfile" --tag sanctuary-bundle-builder "$trusted"
docker run --platform linux/amd64 --rm --init --read-only --cap-drop ALL --security-opt no-new-privileges \
    --user 65532:65532 --pids-limit 1024 --cpus 2 --tmpfs /tmp:rw,exec,mode=1777 \
    --mount "type=bind,source=$candidate,destination=/source,readonly" \
    --mount type=volume,destination=/work sanctuary-bundle-builder "$base" "$head" \
    > "$destination" 2> "${RUNNER_TEMP:?}/bundle-build.log"
test -s "$destination"
test "$(wc -c < "$destination")" -le 536870912
