#!/usr/bin/env bash
# Build one production image in the deployment runner's local Docker store.
set -euo pipefail
component=$1
case $component in
    boxie) file=packages/boxie/infra/Boxie.Dockerfile; context=. ;;
    boxie-sandbox) file=packages/boxie/sandbox/Dockerfile; context=. ;;
    cli-playground) file=tools/cli-playground/infra/docker/CliPlayground.Dockerfile; context=. ;;
    collector) file=packages/boxie/infra/observability/collector/Dockerfile; context=${file%/*} ;;
    *) exit 2 ;;
esac
revision=$(git rev-parse HEAD)
tag="localhost/sanctuary-$component:$revision"
docker buildx build --load --platform linux/amd64 --label "org.opencontainers.image.revision=$revision" \
    --file "$file" --tag "$tag" "$context" >&2
printf '%s\n' "$tag"
