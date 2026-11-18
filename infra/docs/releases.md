# Release and maintain the shared host

## Choose a release

Run either release manually from Actions on `master`:

- [🚀 cli-playground Release](../../.github/workflows/cli-playground-release.yml)
  builds and deploys the cli-playground backend and frontend together in the application image.
- [🚀 Boxie and Sandbox Release](../../.github/workflows/boxie-release.yml)
  builds the Boxie image and sandbox from one commit, then updates Boxie followed
  by its default sandbox image. It does not release the cli-playground application.

A failed stage stops the remaining deployments in its workflow; completed stages
are not rolled back automatically. Boxie stages use the `boxie` environment;
the cli-playground release uses `cli-playground`.
Each stage calls the shared [release transport](../environments/single-host/release.sh) for SSH, image settings
and temporary registry credentials; service scripts own migration and readiness checks.

## What a release changes

The Boxie stage pulls its image, stops API and supervisor, runs Alembic migration,
and starts both services with the metrics overlay. PostgreSQL and Temporal stay
up. Authenticated readiness must pass before the next stage. Pending requests may
resume after the restart; an empty capacity table is not a release condition.
The separate native host acceptance run covers terminal allocation and cleanup.

The sandbox stage changes Boxie's default profile digest and recreates
Boxie's supervisor, preserving other profile fields. The backend stage pulls
and recreates only `backend`; its proxy stays up.

## Queue and retry behavior

Setup and release workflows share one `sanctuary-production` queue. Each run selects
current `master` after entering the queue, then builds and deploys that checkout.
If a run fails, choose **Re-run all jobs** or start a new workflow run. Re-running
only failed jobs keeps the earlier source selection and is rejected before
deployment or provisioning starts.

Builds can run before production activation; deployments still require
`DEPLOYMENT_ACCEPTANCE_PASSED`. Pushes do not
trigger releases.

## Verify distribution notices before publishing

Inspect the final Linux amd64 images before starting a release or setup run.
Those workflows can publish images before deployment is approved. Build and
inspect the three images with application notice bundles from the repository root.

```sh
uv run --locked pytest infra/environments/single-host/tests/test_distribution_notices.py \
  -m integration -k release_container_notices
```

| Image or package | Where to inspect notices |
| --- | --- |
| Boxie and cli-playground images | `/usr/share/sanctuary/notices` contains the application and base Python inventories, wheel notices, CPython license, native-wheel review and OS package index. Boxie also includes the capture executable notices. The playground includes the Vite report and Tailwind CSS license from its built static assets. |
| Collector image | `/usr/share/sanctuary/notices/vector` contains the notice, copyright, dependency list and license texts from the same upstream image as the shipped Vector executable. |
| All four images, including the sandbox | `/usr/share/doc/<package>/copyright` and `/usr/share/common-licenses` contain the Debian or Ubuntu package notices. In the sandbox, run `dpkg-query -W` to identify the installed packages and versions. |
| Locally built service wheels | Open the wheel as a ZIP. Boxie's capture notices sit beside both executables under `boxie/sandbox/capture_bins/`. Build the frontend before building the playground wheel, then inspect `cli_playground/static/` for `licenses.md` and `tailwindcss.LICENSE`. |

For a dependency update, compare two clean builds using the same resolved base
digests, OS package versions and lockfiles. Compare the paths and file contents
in the notice bundles. For a missing notice, check the exact target wheel or
upstream image and restore the upstream text for the version that ships.

For the Boxie and playground images, open `native-wheel-review.json` from
the local build. The review lists shipped shared objects with hashes, upstream
SBOM entries that lack embedded text, and the exact texts supplied by the
wheels. An SBOM can include build dependencies, so match candidate
components to the wheel's target link inputs before treating their notices as
complete. Record a verified input's object hashes, original notice text and
source under `infra/distribution/vendor/native/` for the exact wheel version.
The production image build sets `NATIVE_NOTICE_POLICY=require-complete`
and fails before pushing a service image with unresolved native inputs. Use
the exact wheel build to resolve each outstanding input before publishing.
[Issue #201](https://github.com/di-rs/sanctuary/issues/201) tracks the gate.

Find Rust notices alongside the same revision's binary artifact. Follow the
[preview download procedure](../../tools/cli-playground/docs/previews.md#download-notices-with-a-preview-build)
to verify the companion against the extracted executables.

## Inspect a failed release

An unsuccessful SSH or Compose command fails the Actions run. On the host, inspect
services and recent logs before rerunning the workflow:

```sh
docker compose --env-file /etc/sanctuary/boxie.env --env-file /etc/sanctuary/boxie-image.env \
  -f /opt/sanctuary/boxie/compose.production.yml -f /opt/sanctuary/boxie/compose.operations.yml \
  -f /opt/sanctuary/boxie/compose.observability.yml ps
docker compose --env-file /etc/sanctuary/boxie.env --env-file /etc/sanctuary/boxie-image.env \
  -f /opt/sanctuary/boxie/compose.production.yml -f /opt/sanctuary/boxie/compose.operations.yml \
  -f /opt/sanctuary/boxie/compose.observability.yml logs --tail 100 api supervisor
docker compose --env-file /etc/sanctuary/cli-playground.env --env-file /etc/sanctuary/cli-playground-image.env \
  -f /opt/sanctuary/cli-playground/compose.production.yml ps
```

A migration failure leaves Boxie's API and supervisor stopped. Check migration
output and database state before retrying; do not start an older application
against a newer schema. After an SSH interruption, first check whether Compose
finished the operation and whether the application is healthy. Fix the cause and
rerun the workflow. There is no automatic rollback or separate deployment state
to clear.

## Acceptance and maintenance

Run local checks from the repository root:

```sh
uv sync --all-packages
uv run pytest infra/host/tests infra/environments/single-host/tests \
  packages/boxie/tests/test_deployment.py tools/cli-playground/tests/test_deployment.py \
  tools/cli-playground/tests/test_infra_workflows.py
```

On an authorized native Linux amd64 host, exercise fresh setup, an unchanged
rerun, both release workflows, migration failure and retry, metrics, tunnel
configuration and preview publication. The local command tests cannot establish
those host behaviors. The [host requirements](../../packages/boxie/docs/deployment.md#deployment-prerequisites)
include the runsc and backup checks.

## Certificates and backups

The generated Boxie TLS leaf certificates last 90 days and the CAs last 365 days.
Plan renewal separately. Maintain an off-host backup and rehearse restoration
before relying on recovery; the protected disk alone is not a
backup.
