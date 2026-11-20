# Sanctuary threat model

Use this model for changes to input handling, authentication, sandboxing,
persistence, CI publication, or infrastructure. Protect host integrity, session
and consumer isolation, credentials, artifact integrity, lifecycle state, and
service availability. User files and terminal contents may contain sensitive data.

Advisory secret scans must not publish credential values and run without credential verification or container network access.

## Trust boundaries

- **Operator to dashboards:** Cloudflare Access checks the operator's exact email. Each administration hostname has its own audience enforced by the tunnel connector. Grafana verifies the signed assertion against its configured issuer, audience and email. Temporal UI has broad workflow visibility. Treat dashboard contents as private and untrusted. [Administration](../infra/docs/setup.md#configure-ingress-and-your-admin-identity)
- **Local CLIs:** Arguments, stdin, files, and filenames are untrusted. Commands
  run with the invoking user's permissions; parsing must not cause unintended
  reads, writes, or execution.
  Kara's atomic saves must preserve existing owner, group, mode, and access ACLs
  or fail before replacement. Staging files must not expose content through inherited
  access rules. Errors after replacement must report committed data with uncertain
  durability rather than an unchanged destination.
- **Browser to playground:** HTTP requests and terminal frames are untrusted.
  [Routes](../tools/cli-playground/src/cli_playground/routes.py) check origins and
  session bindings. Preserve session authorization across reconnects and revision
  changes. Origin checks do not authenticate arbitrary clients or prevent abuse.
- **Playground to Boxie:** The [private API](../packages/boxie/README.md) derives
  consumer identity from credentials and enforces resource ownership. Keep
  consumer and supervisor credentials separate and out of browser responses.
  Operators grant job profiles to individual consumer IDs. Job consumers
  select an owned artifact and an exact command from a granted profile. Treat
  captured stdout and stderr as private consumer data in PostgreSQL and backups.
  Reserve output storage at admission and bound concurrent downloads per consumer
  and across the installation's API process. Enforce ownership and expiry on
  reads. Preserve submission keys after result expiry and
  require a new explicit submission when an authorized start has an unknown outcome.
- **Artifacts to host storage:** ZIPs and executable bytes remain untrusted after
  admission. Preserve path/type validation and expanded-byte limits in
  [Boxie extraction](../packages/boxie/src/boxie/persistence/artifact_files.py)
  and [playground validation](../tools/cli-playground/src/cli_playground/artifacts.py).
  Enforce consumer and installation artifact budgets on the owning supervisor.
  Keep staging and retired bytes charged until publication or physical cleanup
  settles the reservation. A lost acknowledgement can leave bytes on disk.
  Resolve it against PostgreSQL before collecting or releasing capacity.
  Valid executable headers do not establish trust. The optional command catalog
  is untrusted data with bounded bytes, tree size, strings, names and collections.
  Bind it to the expected head revision and exact executable digests. Persist its
  canonical digest in both upload intents and immutable revisions, including
  conflict checks on retries and recovery. Strip the sidecar before sending the
  executable bundle to Boxie. [Publication contracts](../tools/cli-playground/docs/previews.md#build-and-comparison-contract)
  define the limits and unavailable-baseline behavior.
- **Catalog to browser and terminal:** Render metadata as text, never HTML.
  Shell-quote inserted tokens and reject control characters; never append Enter
  or placeholder operands. Changing the explorer must not replace a session or
  silently change the revision described. Digests establish artifact identity,
  not the truth of descriptions or the completeness of behavior-change badges.
  The command builder reads echoed shell drafts from xterm after OSC 133 prompt
  markers. These sandbox-controlled markers are advisory UI state, not a security
  boundary. Builder clicks send only a fixed Readline clear-line binding followed
  by validated, shell-quoted text; never derive terminal control sequences from
  metadata. Disable builder edits outside the observed prompt. Do not log drafts
  or send them to external search or telemetry services.
- **Sandbox to host:** Only the supervisor receives Docker access. Preserve
  [runsc isolation](../packages/boxie/src/boxie/sandbox/docker.py), the non-root
  user, disabled network, read-only root and artifacts, dropped capabilities,
  and resource limits, including during recovery. The supervisor supplies the
  read-only job capture executable. The workload can write to its output pipes.
  Only the capture process should be able to publish the completion record on
  the Docker stream.
- **PR metadata to repository labels:** The pinned third-party label action reads
  trusted base-revision configuration with contents-read and PR-write permissions.
  Treat PR bodies, filenames, and event payloads as data; never execute PR code or
  interpolate these values into shell scripts. Author selections cannot request
  draft CI. Labels are advisory and do not replace branch protection.
- **PR build to publication:** PR source and build outputs are untrusted.
  The [privileged controller](../.github/workflows/cli-playground-preview.yml)
  uses default-branch code. Never execute PR-controlled scripts or binaries with
  publication or deployment credentials. Apply the same boundary to benchmark
  reporting and release automation. CLI reflection runs only in the unprivileged
  build, with elapsed-time/output limits and without ambient credentials; the
  publisher and gateway validate metadata without executing uploaded code.
  Contributors run selected browser demos inside the disposable local playground and
  publish WebM recordings of synthetic session data. Treat the checkout and its
  build scripts as trusted local code. PR policy only reads the attachment links.
- **Local fixture recipes and recordings:** CLI test catalogs and their reference
  commands are trusted repository code, executed with the developer's permissions.
  Marked CLI README examples run as test code under the same permissions locally
  and in the unprivileged PR test jobs.
  Temporary test workspaces do not sandbox host access. `cli-testing record`
  stages output outside committed fixtures; `apply` is an explicit promotion of a
  reviewed capture. Validate catalog ownership, allowed paths, input/expectation
  hashes, reference identity, completion, and shared-file conflicts before writes.
  A recording's provenance is consistency metadata, not authentication of an
  arbitrary downloaded artifact.

## Review priorities

Trace attacker-controlled input to the affected asset; state required credentials,
reachability, impact, and the control bypassed. Prioritize cross-session or
cross-consumer access, sandbox escape, archive traversal, resource exhaustion,
secret disclosure, and privileged execution of PR-controlled code.

Check rejected requests, stale attachments, retries, and recovery. Failures must
not leave unauthorized sessions, published files, or indefinite capacity
reservations. Keep terminal contents and credentials out of logs and metrics.
Distinguish local CLI failures from remotely reachable service vulnerabilities.

Source badge generation runs with read-only access; its write-capable publisher never executes repository code or artifact contents.

## Deployment assumptions

The single Hetzner host pulls desired releases from a private R2 bucket with a read-only credential. Protected release workflows alone select deployable images and service configuration. The preview build container mounts only PR source and disposable storage. The staging URL permits one object and stays outside the container. A fresh runner compares the staged bytes to the build digest and checks live eligibility before publishing. The host verifies every digest. A preview manifest selects an untrusted binary bundle and a bounded lease. The protected production gateway remains responsible for validating archive contents.

PostgreSQL, Temporal, Boxie and observability use private networks. Each gateway has a distinct database login and bearer key; Boxie reads live key hashes from an operator-owned directory. Deployment and drain routes stay private. On preview removal the controller revokes the existing key, withdraws the route, drains outstanding operations and drops that preview's data. The daily database backup leaves the host encrypted with the operator's public key. [Service boundaries](../infra/docs/architecture.md)

The opt-in [playground development Compose stack](../tools/cli-playground/compose.dev.yml)
uses real CLI binaries and PTYs inside one non-root container, backed by the
terminal transport test harness. It is for trusted local code and disposable data,
not untrusted PR execution: sessions share a container and its private development
network, and have no gVisor or Temporal isolation. Publish only its loopback UI
port; never mount host directories, production credentials, or the Docker socket.
The local-dev launcher scopes Compose resources by canonical worktree path; Docker
allocates the published loopback port. Session files use a Docker-managed, project-scoped volume removed by `local-dev down`. PostgreSQL remains private to each project.
Its development-only adapter translates loopback Host ports to the internal
authority after requiring any Origin to match the original Host exactly. It
rejects non-loopback hosts and duplicate authorities; production host validation
is unchanged. Its runner lives outside the installed playground package and
production images.

The intended topology exposes only the playground. Confirm that Boxie,
Docker, PostgreSQL, Temporal, and metrics remain private; verify TLS, proxy/Host
handling, authentication, and operator-only writes to profiles and storage.
Confirm native Linux/gVisor enforcement rather than assuming container isolation.

Public admission rate limits, credential rotation, backup access, and retention
need operator confirmation. Capacity limits alone do not establish abuse controls.
An already-compromised operator, host kernel, or Docker daemon is outside this
application-level model; paths for untrusted inputs to gain that access are in scope.

Update this model when boundaries or deployment assumptions change. This file
informs repository reviews; it does not configure Codex Security Cloud monitoring.
Its structure follows [OpenAI's threat-model guidance](https://learn.chatgpt.com/docs/security/threat-model).
