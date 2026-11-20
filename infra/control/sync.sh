#!/bin/bash
set -euo pipefail
cd /opt/sanctuary
# Use only the protected default branch for host programs. A registry outage
# still lets the controller revoke locally expired keys.
if git fetch --no-tags origin master; then
    git merge --ff-only origin/master
fi
exec python3 -m infra.control.host sync
