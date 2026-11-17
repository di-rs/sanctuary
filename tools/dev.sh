#!/bin/sh
# Compatibility entry point; implementation lives in the local-dev Python package.
set -eu
dev_root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
cd "$dev_root"
if [ "$#" -eq 0 ]; then set -- up; fi
if [ "$1" = help ]; then shift; set -- --help "$@"; fi
exec uv run local-dev "$@"
