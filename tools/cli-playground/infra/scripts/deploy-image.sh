#!/usr/bin/env bash
# A repeated source image needs a rebuild to run the release process again.
set -euo pipefail
app=$1 image=$2 method=$3
dokku() { docker exec -i sanctuary-dokku dokku "$@"; }
current=$(dokku git:report "$app" --git-source-image </dev/null)
if [[ $current == "$image" ]]; then
    if [[ $method == git:load-image ]]; then docker image load; fi
    dokku ps:rebuild "$app" </dev/null
else
    dokku "$method" "$app" "$image"
fi
