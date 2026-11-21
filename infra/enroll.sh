#!/bin/bash
# Run once from the existing server's provider console in the protected checkout.
set -euo pipefail
test "$(id -u)" = 0
test "$(uname -m)" = x86_64 || { echo 'Boxie currently accepts x86-64 Linux CLI bundles.' >&2; exit 1; }
cd /opt/sanctuary
test "$(git branch --show-current)" = master
test -z "$(git status --porcelain --untracked-files=no)"
test -r /etc/sanctuary/host.env && test -r /etc/sanctuary/backup.env
chmod 700 /etc/sanctuary
chmod 600 /etc/sanctuary/{host,backup}.env
# The operator owns this file. It contains simple shell-compatible assignments.
set -a
# shellcheck source=/dev/null
. /etc/sanctuary/host.env
set +a
for credential in "$TUNNEL_TOKEN_FILE" "$ALERT_WEBHOOK_FILE"; do
    test -s "$credential" && test ! -L "$credential"
    test "$(dirname "$(realpath "$credential")")" = /etc/sanctuary
done
# Their root-only parent keeps these single-file container bind mounts private.
chmod 444 "$TUNNEL_TOKEN_FILE" "$ALERT_WEBHOOK_FILE"
# shellcheck source=/dev/null
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = "24.04"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl openssl age python3-venv git
if ! command -v docker >/dev/null; then
    apt-get install -y docker.io docker-compose-v2
fi
if ! docker compose version >/dev/null; then
    apt-get install -y docker-compose-v2
fi
systemctl enable --now docker
if ! docker info --format '{{json .Runtimes}}' | python3 -c 'import json,sys;sys.exit("runsc" not in json.load(sys.stdin))'; then
    stage=$(mktemp -d)
    for file in runsc containerd-shim-runsc-v1; do
        url="https://storage.googleapis.com/gvisor/releases/release/${GVISOR_RELEASE:-latest}/x86_64/$file"
        curl -fsSL "$url" -o "$stage/$file"
        curl -fsSL "$url.sha512" -o "$stage/$file.sha512"
        (cd "$stage" && sha512sum --check "$file.sha512")
        install -m 755 "$stage/$file" "/usr/local/bin/$file"
    done
    runsc install
    systemctl reload docker
    docker info --format '{{json .Runtimes}}' | python3 -c 'import json,sys;sys.exit("runsc" not in json.load(sys.stdin))'
fi
python3 -m venv /opt/sanctuary-tools
/opt/sanctuary-tools/bin/pip install --disable-pip-version-check awscli==1.42.0
install -d -m 700 "${SANCTUARY_STATE:-/var/lib/sanctuary}"
bash infra/control/credentials.sh
install -m 644 infra/control/systemd/sanctuary-* /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sanctuary-sync.timer sanctuary-backup.timer
