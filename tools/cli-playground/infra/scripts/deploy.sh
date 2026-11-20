#!/usr/bin/env bash
# Dokku runs the image's release process before scheduling its single web worker.
set -euo pipefail
config=${SANCTUARY_CONFIG_DIR:-/etc/sanctuary}
# shellcheck disable=SC1091
source "$config/settings.env"
if (( $# )); then
    [[ $# == 1 && $1 =~ ^localhost/sanctuary-cli-playground:[a-f0-9]{40}$ ]]
    bash "$(dirname "$0")/deploy-image.sh" cli-playground "$1" git:load-image
else
    # Setup has already loaded and verified all four images.
    # shellcheck disable=SC1091
    source "$config/cli-playground-image.env"
    bash "$(dirname "$0")/deploy-image.sh" cli-playground "$CLI_PLAYGROUND_IMAGE" git:from-image
fi
for attempt in {1..60}; do
    if docker exec cli-playground.web.1 /app/.venv/bin/python -c '
import os, pathlib, urllib.request
token = pathlib.Path(os.environ["CLI_PLAYGROUND_BOXIE_CREDENTIAL_FILE"]).read_text().strip()
request = urllib.request.Request(os.environ["CLI_PLAYGROUND_BOXIE_URL"] + "/readyz", headers={"Authorization": "Bearer " + token})
urllib.request.urlopen(request, timeout=5).close()'; then break; fi
    (( attempt < 60 )) || exit 1
    sleep 5
done
curl --fail --silent --show-error --retry 60 --retry-all-errors --retry-delay 5 --max-time 10 \
    "https://$CLI_PLAYGROUND_DOMAIN/healthz"
