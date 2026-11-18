# Configure Boxie processes

Configure the supervisor and API separately. Provision PostgreSQL, Temporal,
and a native Linux/gVisor host using the [infrastructure guide](deployment.md)
before running these commands. Both endpoints must remain private.

## Start the supervisor

Use the root workspace and lockfile:

```sh
uv sync --all-packages
uv run --package boxie boxie-supervisor --config /etc/boxie/supervisor.json
```

An operator configuration file contains:

```json
{
  "data_dir": "/var/lib/boxie",
  "postgres_dsn_file": "/run/secrets/postgres-dsn",
  "lifecycle": {
    "postgres_dsn_file": "/run/secrets/postgres-dsn",
    "temporal_address": "temporal:7233",
    "temporal_server_name": "temporal",
    "temporal_ca_file": "/run/secrets/temporal-ca.pem",
    "temporal_cert_file": "/run/secrets/temporal-client.pem",
    "temporal_key_file": "/run/secrets/temporal-client.key"
  },
  "profiles_file": "/etc/boxie/profiles.json",
  "credential_file": "/run/secrets/boxie-supervisor",
  "identity": {
    "installation_id": "b18283b1-dc32-46e7-8da5-7aa380043685",
    "host_id": "sandbox-1"
  },
  "bind_host": "127.0.0.1",
  "bind_port": 8091
}
```

### Identity and credentials

Generate a unique installation UUID once and preserve it with the data directory.
The credential is a separate supervisor-control secret, at least 16 printable ASCII
bytes, in a private regular file (mode `0600`). Consumer API credentials must not
be reused here. Access logging is disabled by the entry point; credentials are
never accepted in URLs.

## Start the API

Run the separate consumer API without a Docker socket or artifact host mounts:

```sh
uv run --package boxie boxie-api --config /etc/boxie/api.json
```

Its operator configuration contains:

```json
{
  "supervisor_url": "http://boxie-supervisor:8091",
  "supervisor_credential_file": "/run/secrets/boxie-supervisor",
  "consumer_credential_files": {
    "example-consumer": "/run/secrets/consumer"
  },
  "job_policy": {
    "profile_grants": {"example-consumer": ["batch"]},
    "consumer_result_bytes": 268435456,
    "total_result_bytes": 1073741824,
    "consumer_downloads": 2,
    "total_downloads": 4
  },
  "release": "boxie",
  "identity": {
    "installation_id": "b18283b1-dc32-46e7-8da5-7aa380043685",
    "host_id": "sandbox-1"
  },
  "lifecycle": {
    "postgres_dsn_file": "/run/secrets/postgres-dsn",
    "temporal_address": "temporal:7233",
    "temporal_server_name": "temporal",
    "temporal_ca_file": "/run/secrets/temporal-ca.pem",
    "temporal_cert_file": "/run/secrets/temporal-client.pem",
    "temporal_key_file": "/run/secrets/temporal-client.key"
  },
  "request_timeout": 20,
  "bind_host": "127.0.0.1",
  "bind_port": 8090
}
```

### Consumer credentials and transport

Each credential is a private regular file with the same restrictions as the supervisor
secret. Consumer credentials must be unique and distinct from the supervisor secret.
The API resolves consumer identity from Bearer authentication and never accepts
consumer identity in a sandbox request body.

Grant each consumer the job profiles it may submit in `job_policy.profile_grants`.
An omitted consumer starts with no job profiles. Restart the API to apply a
grant change. Removing a grant prevents new submissions and preserves access to
previously accepted jobs and their results. On a configuration generator rerun,
omitting `--job-profile` preserves the current grants. Passing one or more
`--job-profile` arguments replaces the list for the selected `--consumer-id`.
To revoke the last grant, set that consumer's list to `[]` in `api.json` and
restart the API.

The example shows the default result budgets. PostgreSQL reserves the profile's
output limit for each pending job, then charges the actual combined stdout and
stderr bytes until the result is deleted. By default one consumer can reserve
256 MiB and all consumers combined can reserve 1 GiB. The API process allows
two simultaneous result downloads for one consumer and four in total. A slow
client holds its slot until the response finishes or the connection closes.

HTTP and WebSocket redirects are disabled for supervisor calls. HTTP control bodies
and responses are bounded to 64 KiB; uploads stream in chunks of at most 64 KiB
with an actual-byte ceiling of 512 MiB and a configured total request deadline.

## Default environment

Boxie owns one Ubuntu 24.04 Linux x86_64 environment with Bash, standard utilities
and built-in file fixtures. Uploaded files are mounted read-only at `/opt/artifact`, which is on PATH; built-in fixtures seed the
writable `/workspace`. Uploaded files never replace shell startup configuration.
The shell disables Bash's `true` and `false` builtins when uploaded executables
use those names. Workspace files remain non-executable.

### Choose the sandbox image

The operator installs the Boxie sandbox image using `BOXIE_SANDBOX_IMAGE`. The
internal profile file is not a consumer interface. It contains one `default`:

```json
{
  "default": {
    "image_digest": "registry.example/boxie-sandbox@sha256:1111111111111111111111111111111111111111111111111111111111111111",
    "commands": [["/opt/boxie/shell.sh"]],
    "env": {"TERM": ["xterm-256color"]},
    "artifact_target": "/opt/artifact"
  }
}
```

Replace the example image digest with the approved Boxie sandbox image. Local content-addressed
image IDs (`sha256:` plus 64 lowercase hex digits) are also accepted. Commands
are exact argument-vector allowlists; environment keys and values are allowlists.
The artifact mount must be a normalized path under `/opt/`. Optional `limits`
may lower the defaults but cannot increase them.

For a noninteractive job, add a profile such as `batch` using an approved image
digest and an exact command entry such as
`["/usr/bin/wc", "-c", "/opt/artifact/input.txt"]`. Grant `batch` in the API
configuration and give the consumer the profile ID and argument vector.
Job requests supply an owned artifact and use
the approved image environment. The profile's `limits.output_bytes` caps the
combined stored stdout and stderr before base64 encoding.
Job profiles need `limits.pids` of at least 2 and `limits.nofile` of at least 9.
The capture program runs alongside the command and opens three pipes before launch.
Boxie rejects new jobs below either minimum with HTTP 422.

### Reload profiles

Send `SIGHUP` to validate and atomically reload all profiles. A failed reload keeps the last valid version.
Approved versions are retained by configuration hash, including across supervisor
restarts, so delayed requests can validate their original snapshot. Reloads never
change an admitted sandbox's image, command, environment, or limits.
