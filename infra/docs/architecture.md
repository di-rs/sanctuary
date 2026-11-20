# Service boundaries

The first installation uses one existing Hetzner host. Each row has its own Compose project and release manifest. Production and preview gateways run the same trusted application image. Each preview supplies a different CLI bundle.

| Project | Responsibility | Consumers |
| --- | --- | --- |
| Edge | Cloudflare Tunnel and Caddy hostname routing | Browsers |
| Playground | Browser sessions, CLI catalog, deployment metadata | Production visitors |
| One Playground per eligible PR | PR-specific gateway, data directory, database login, expiring Boxie key | Preview visitors |
| Boxie | Private authenticated API and supervisor, eight sandbox slots, Docker and gVisor | The gateways |
| Temporal | Workflow service, two SQL schemas, operator UI | Boxie API and supervisor over mutual TLS |
| Observability | OTLP collector, Tempo traces, Loki logs, Prometheus, Alertmanager and Grafana | Instrumented services and the operator |
| PostgreSQL | One cluster with separate login roles and databases for Boxie, Temporal and each gateway | Each database's owner |

Only the supervisor has the Docker socket. Interactive workloads run inside network-isolated gVisor sandboxes. Production can use the entire slot pool. Two slots are reserved for production and each preview can hold one. API ownership checks bind sandboxes and artifacts to the authenticated consumer. The system assigns a separate consumer key to every gateway.

Boxie reads `BOXIE_TEMPORAL_ADDRESS`, `BOXIE_TEMPORAL_NAMESPACE`, `BOXIE_TEMPORAL_SERVER_NAME` and `OTEL_EXPORTER_OTLP_ENDPOINT` from its environment. Its client identities and CA trust are read-only mounts. The gateway reads its private `CLI_PLAYGROUND_BOXIE_URL` and credential file. The host setting `BOXIE_URL` supplies the current endpoint to gateways. Moving a dependency requires deploying its endpoint and corresponding trust material, then recreating its consumers. A host outage affects every local project.

Builds run on GitHub-hosted runners. The host initiates outbound connections to the protected source branch and the private delivery bucket. It verifies SHA-256 before loading trusted application images or streaming a PR bundle into the gateway. PR source, CI commands and Compose manifests from feature branches stay off the host. [Release controller](../control/host.py) · [Service manifests](../services)
