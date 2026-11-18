# Debug production with Codex and MCP

Local Codex Desktop and CLI can read Sanctuary's Grafana dashboards and inspect
Temporal workflows in the `boxie` namespace. Both use the Model Context Protocol
(MCP). Codex starts the requested adapter over SSH on the production host, where
the Grafana Viewer token and Temporal client certificate stay.

## Connect Desktop and CLI

Run the commands on the computer where Codex runs, as the user who runs it.
Desktop and CLI sessions that use the same Codex home share these registrations.
If you already have both entries, go straight to [verify the connection](#verify-the-connection).

Use an SSH alias for your authorized production operator. The examples call it
`sanctuary-production`. Configure the host, user and identity for that alias
in `~/.ssh/config` and verify the server's host key through your normal operator
channel. The operator needs Docker access and permission to read
`/etc/sanctuary/boxie.env`. Check that SSH works without a prompt and that the
shared-host installer has installed the launcher. This command succeeds silently.

```sh
ssh -T -o BatchMode=yes -o StrictHostKeyChecking=yes sanctuary-production \
  'test -x /usr/local/bin/sanctuary-mcp && test -r /etc/sanctuary/boxie.env && docker info >/dev/null'
```

Register each adapter once. Keep `-T` so the SSH connection carries the MCP
messages over standard input and output.

```sh
codex mcp add production-grafana -- \
  ssh -T -o BatchMode=yes -o StrictHostKeyChecking=yes sanctuary-production \
  /usr/local/bin/sanctuary-mcp grafana
codex mcp add production-temporal -- \
  ssh -T -o BatchMode=yes -o StrictHostKeyChecking=yes sanctuary-production \
  /usr/local/bin/sanctuary-mcp temporal
```

## Verify the connection

Run `codex mcp get production-grafana` and `codex mcp get production-temporal`.
Both should show an enabled stdio server with `ssh` as the command. Then open a
new Desktop chat on the configured host or start a new `codex` CLI session.
These two requests exercise the production credentials and backend services.

| Ask Codex | Expected result |
| --- | --- |
| Use `production-grafana` to call `get_dashboard_by_uid` for `boxie-operations`. Return the title and UID. | **Boxie operations**, UID `boxie-operations`. |
| Use `production-temporal` to call `check_connection` with target `production`. Report each stage. | The server and namespace stages return `ok`. The codec stage is skipped because this target omits workflow payloads. |

## Investigate a production issue

Start with the *Boxie operations* dashboard for the incident time window. Ask
Codex to inspect the relevant panel and its Prometheus query. For a delayed job,
give Codex the workflow ID and time window and ask it to inspect the execution
in Temporal. For an individual HTTP failure, take the response's `X-Request-ID`
to Grafana Explore and query VictoriaLogs there. [Trace requests across services](../infra/docs/observability.md)

## Troubleshoot the connection

| Symptom | What to check |
| --- | --- |
| A new chat cannot find the server | Run the two `codex mcp get` commands on the host selected in Desktop. Check the local user, Codex home, SSH destination and adapter name. |
| SSH reports a host-key error or `Permission denied` | Run the SSH check above from the same account. Verify a changed fingerprint with the host administrator. Check the alias's user and identity, and make sure the key is available for noninteractive use. |
| SSH works but MCP fails to initialize | Confirm the launcher, environment file and Docker access with the SSH check above. A remote shell that prints a banner to stdout on noninteractive sessions can corrupt MCP messages. [Adapter installation](../packages/boxie/docs/mcp.md#deploy-through-the-existing-workflow) |
| Grafana returns 401 or 403 | Check the deployed `sanctuary-mcp` service account and its Viewer token. The installer validates both. [Grafana credential recovery](../packages/boxie/docs/mcp.md#recover-or-remove-access) |
| Temporal reports a failed stage | Start with the first failing stage. For `server`, check the Temporal service and its operator TLS certificates. For `namespace`, check that the `boxie` namespace exists. [Temporal operations](../packages/boxie/docs/temporal.md) |

To disconnect these tools from local Codex, run `codex mcp remove production-grafana`
and `codex mcp remove production-temporal`, then start a fresh session.
