# Boxie and Temporal

Sanctuary deploys Temporal independently. Boxie uses its namespace for sandbox lifecycle and maintenance work. The Boxie namespace job creates or verifies the namespace with seven-day workflow retention before starting the API and supervisor.

## Trust and private transport

The frontend and internode connections require valid client certificates from the installation CA. Boxie mounts different leaf identities for its API, worker and namespace operation. Its client checks the server name against the trusted CA. Set the Temporal address, expected server name and namespace through the [host environment](../../../infra/host.env.example). The Temporal UI has its own client identity. Cloudflare Access restricts its browser origin to the operator.

The persistence server and schema tools use a private PostgreSQL login that owns the `temporal` and `temporal_visibility` databases. The Playground and Boxie roles have separate database ownership. [Temporal service definition](../../../infra/services/compose.temporal.yml) · [First deployment](../../../infra/docs/setup.md)
