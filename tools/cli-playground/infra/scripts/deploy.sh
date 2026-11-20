#!/usr/bin/env bash
# Reconcile the platform, then replace only the production Dokku app.
set -euo pipefail
[[ $# == 0 ]] || exit 2
config=${SANCTUARY_CONFIG_DIR:-/etc/sanctuary}
owner=${SANCTUARY_CLI_PLAYGROUND_DIR:-/opt/sanctuary/cli-playground}
set -a
# shellcheck disable=SC1091
source "$config/cli-playground.env"
# shellcheck disable=SC1091
source "$config/cli-playground-image.env"
set +a
bash "$owner/scripts/install.sh"
python3 "$owner/cli_playground_infra/dokku.py" deploy --image "$CLI_PLAYGROUND_IMAGE"
container=$(docker ps -q --filter label=com.dokku.app-name=cli-playground --filter label=com.dokku.process-type=web)
[[ -n $container && $container != *$'\n'* ]]
if docker exec -i "$container" /app/.venv/bin/python - <<'PY'
import os
import time
from urllib.error import URLError
from pathlib import Path
from urllib.request import Request, urlopen

credential = Path(os.environ['CLI_PLAYGROUND_BOXIE_CREDENTIAL_FILE']).read_text().strip()
request = Request(os.environ['CLI_PLAYGROUND_BOXIE_URL'].rstrip('/') + '/readyz',
                  headers={'Authorization': 'Bearer ' + credential})
deadline = time.monotonic() + 300
while True:
    stage = 'authenticated Boxie readiness'
    try:
        with urlopen(request, timeout=10) as response:
            if response.status != 200:
                raise ValueError('unexpected status')
        break
    except (URLError, OSError, ValueError) as error:
        if time.monotonic() >= deadline:
            raise SystemExit(f'{stage} failed after 300 seconds: {error}') from error
        print(f'Waiting for {stage}: {error}', flush=True)
        time.sleep(5)
PY
then
    :
else
    status=$?
    docker logs --tail 80 "$container" >&2 || true
    exit "$status"
fi
