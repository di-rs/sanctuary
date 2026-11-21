# Deploy the CLI Playground

Use **Deploy Playground** in GitHub Actions to build the trusted website and its production CLI bundle. Sanctuary runs the gateway on a private network and exposes it through Cloudflare Tunnel. Each gateway owns its SQL database, deployment token and Boxie consumer key. A production release also supplies the trusted web image used by preview gateways. [First deployment](../../../infra/docs/setup.md) · [Release operations](../../../infra/docs/releases.md)

The container runs its schema migration before starting the web process. It reads the public origin, Boxie endpoint and credential file, and database URL from its own configuration. The reverse proxy exposes terminal and catalog routes. Deployment routes are private. [Database lifecycle](database.md) · [Configuration](../README.md#configure-the-backend)
