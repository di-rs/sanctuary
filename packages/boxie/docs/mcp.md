# Connect production tools to Codex and ChatGPT

The production MCP adapters let an assistant inspect Grafana dashboards and
Prometheus metrics, and investigate Temporal workflows in the `boxie` namespace.
They run on demand over standard input/output inside private Docker networks.
No MCP listener, public port, DNS record, or Cloudflare Access exception is added.

The shared-host setup workflow installs the adapters from this repository.
Pulumi continues to manage the host and operator access; Compose manages these
processes alongside the existing services. Local Pulumi credentials are not
required. Installing the adapters does not connect either assistant automatically.

## Deploy through the existing workflow

Merge the change to `master`, then run **Single-host Sanctuary setup** in GitHub
Actions from `master`, following the [shared-host setup guide](../../../infra/docs/setup.md).
This is the full existing provisioning workflow: review its scope before running
it, because it also reconciles cloud resources and restarts supporting services.
It uses the production Pulumi backend and credentials in the `sanctuary` environment.

After Grafana starts, setup pulls the pinned adapter images, creates an enabled
`sanctuary-mcp` Grafana service account with the Viewer role, and stores its token
at `/etc/sanctuary/mcp/grafana-token`, mode 0600, owned by UID 472. The one-time
bootstrap container receives the Grafana admin password. The running Grafana
adapter receives only the Viewer token. Repeated setup validates and retains the
token; it fails if the account has elevated privileges, is disabled, or the token
belongs to another identity.

Setup installs `/usr/local/bin/sanctuary-mcp`, which accepts `grafana` or `temporal`.
It launches an ephemeral container, preserves stdin, and reserves stdout for MCP
messages. Use it through a client rather than running it as an interactive shell.

Grafana enables only dashboard/search, datasource and Prometheus tools, with
writes and usage telemetry disabled. VictoriaLogs querying is not included.
Temporal is pinned to the upstream read-only **0.0.6 pre-release** and omits
workflow payload data. Failure messages and search attributes can still contain
application information. Its mounted operator certificate is accepted by the
self-hosted Temporal server, which has no per-operation authorizer: read-only
behavior is enforced by the adapter, not by the certificate's privileges.

## Connect Codex through SSH

The current deployment uses the root operator to launch the read-only adapters.
Use the local operator guide to register both tools, verify a real read and
diagnose connection failures. [Debug production with Codex and MCP](../../../docs/production-mcp.md)

## Connect ChatGPT through a private tunnel

ChatGPT cannot use the local SSH command directly. Use OpenAI's
[Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
to relay MCP requests outbound from the server. The tunnel configuration belongs
to your OpenAI account, separately from this repository's Cloudflare tunnel.

Sign in to the OpenAI Platform and open **Settings → Organization → Tunnels**.
Create one tunnel per adapter and associate both with the intended ChatGPT workspace. Follow
the current OpenAI guide to install `tunnel-client` on the production host and
provide a restricted runtime key through `CONTROL_PLANE_API_KEY`, without placing
the literal key in shell history or this repository. Tunnel setup requires account
permissions and credentials that the Sanctuary deployment does not hold.

For each adapter, initialize and check a profile on the server. For Grafana:

```bash
tunnel-client init --sample sample_mcp_stdio_local \
  --profile sanctuary-grafana --tunnel-id YOUR_GRAFANA_TUNNEL_ID \
  --mcp-command '/usr/local/bin/sanctuary-mcp grafana'
tunnel-client doctor --profile sanctuary-grafana --explain
tunnel-client run --profile sanctuary-grafana
```

Repeat with profile `sanctuary-temporal`, its own tunnel ID, and command
`/usr/local/bin/sanctuary-mcp temporal`. The client processes must remain running
for discovery and tool calls. Account registration and a persistent tunnel-client
service are not installed by the current Sanctuary setup workflow; complete
OpenAI's host-service setup before relying on continuous ChatGPT access.

In [ChatGPT Plugins](https://chatgpt.com/plugins), choose **Add custom MCP server**,
select **Tunnel**, and choose the corresponding tunnel for each adapter. Verify a
dashboard read and Temporal `check_connection` before considering it connected.
Treat tunnel membership as access to production observability data: the adapters
do not authenticate individual callers over their stdio transport.

## Recover or remove access

If setup finds a remote `sanctuary-mcp-read` token without its local file, it stops
instead of silently issuing another token. Revoke that named token in Grafana,
remove any incomplete local token file, then rerun setup. For an expired or revoked
token, remove the local file and the old named token before rerunning. Never print
the token into workflow logs. Certificate renewal follows the existing Temporal
operator certificate lifecycle; the adapter mounts the operator directory.

To stop assistant access, remove the Codex MCP registrations and disable the
OpenAI tunnels. Revoke the Grafana service-account token if its credential needs
to be invalidated. Do not revoke the shared Temporal operator certificate solely
to disconnect an assistant; other operator tools use it too.

Adapter versions and digests live in
[`mcp/compose.yml`](../infra/mcp/compose.yml). Upgrade deliberately and rerun the
MCP integration tests before deploying: newer Temporal releases can change the
available tool set.
