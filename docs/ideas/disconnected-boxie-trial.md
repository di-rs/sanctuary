# Try Boxie on a disconnected Linux host

For a team that reviews every transfer into its build network, a missing
container image can mean another round of approval. A proposed release kit
would let an operator bring Boxie, Sanctuary's sandbox runtime, and its
dependencies onto a disconnected Linux host in one transfer. An application
developer could then submit a first job through the site's private API.

Boxie already disables networking inside each job. On a fresh host, its native
setup fetches build dependencies and builds images from the checkout. Its
shared-host release pulls the image for the API and supervisor, then pulls the
sandbox image in a separate stage.
[Native host setup](../../packages/boxie/docs/deployment.md#configure-a-disposable-native-linux-host)
and [shared-host releases](../../infra/docs/releases.md#what-a-release-changes)

## What E2B and Replicated ship

E2B Embed runs its control plane and Firecracker sandboxes on one Linux host.
Its Compose installer downloads runtime components and reports success once the
first sandbox template is ready. For a Boxie trial, the equivalent milestone
would be an application reading a job result through the private API.
[E2B Embed launch and installation](https://e2b.dev/resources/introducing-e2b-embed)

Replicated ships application and infrastructure assets together for disconnected
installs. Its guide describes how a reference to a multi-architecture image
index can fail when the bundle contains only the x64 image. The Boxie kit
would pin the digest of the individual Linux amd64 manifest in both the
inventory and the destination configuration.
[Replicated air gap installation](https://docs.replicated.com/embedded-cluster/v2/installing-embedded-air-gap)

## From release to first job

Assume a disposable native Linux amd64 host with Docker Engine, Compose,
Python 3 and OpenSSL installed, and gVisor's `runsc` runtime registered with
Docker. Hauler can pack images and files into a portable archive and serve the
images from a read-only registry. The kit would include the Hauler binary
alongside the archive. [Hauler quickstart](https://docs.hauler.dev/docs/getting-started/quickstart)

1. On a connected machine, collect the Boxie and PostgreSQL images along with
   Temporal's server and the admin tools that initialize its schemas.
   Add the sandbox image named in the job profile.
   The supervisor creates that container directly through Docker, so a list of
   Compose services alone would miss it. Pack the Compose definitions and
   bootstrap files for these services, offline instructions and a small job
   client with its sample ZIP.
   [Temporal services](../../packages/boxie/infra/temporal/compose.yml) and
   [sandbox container configuration](../../packages/boxie/src/boxie/sandbox/docker.py)
2. On the target, use a previously trusted public key to verify the signed
   inventory for that release. Check the archive and Hauler binary against the
   listed hashes before using either. Bind the read-only registry to loopback.
   Point the Compose services and the sandbox profile at images in that registry
   by digest. Pull each one before initializing a database.
   [Hauler registry configuration](https://docs.hauler.dev/docs/hauler-usage/store/serve/registry)
3. Generate the service credentials and Temporal certificates on site. Configure
   a batch profile for the byte-count command and grant it to the trial
   consumer. Start PostgreSQL, set up the Temporal schemas, start Temporal and
   create its namespace. Apply the Boxie migration before starting the
   supervisor and API on their private networks.
   [Boxie deployment prerequisites](../../packages/boxie/docs/deployment.md#deployment-prerequisites)

On the private consumer network, the client would authenticate, upload a ZIP
containing `input.txt` with `hello` and a newline, then submit the approved
job. It would print the job ID, state `succeeded`, exit code `0` and a count
of six bytes from decoded stdout. [Byte-count job and result](../../packages/boxie/docs/consumer-api.md#submit-a-job-and-retrieve-its-result)

## Decide whether to package a second release

Give two teams one fresh host each, with an empty Docker image cache and
internet egress blocked before import. Record the bundle size and each
operator's time from transfer to the first correct result. Also try a profile
that names an absent sandbox image. The installer should identify the missing
digest before any schema changes.

Try an upgrade with a returning team if both operators finish with one transfer
each, egress logs show no attempted internet connections from the trial, and at
least one team wants to run its own workload.
