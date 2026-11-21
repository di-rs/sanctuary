# Sanctuary on Hetzner

One existing Linux server runs the public CLI Playground, its PR previews, and a private Boxie instance. Sanctuary operates PostgreSQL, Temporal, and observability as independent Compose projects. Cloudflare Tunnel provides ingress. GitHub Actions publishes releases to private Cloudflare R2 storage.

| Task | Guide |
| --- | --- |
| Enroll the host, configure DNS and restrict the dashboards to your email | [First deployment](docs/setup.md) |
| Deploy one service, find a PR preview, roll back or rotate keys | [Release operations](docs/releases.md) |
| Find traces, configure email notifications and check availability | [Observability](docs/observability.md) |
| Move a dependency or understand the shared failure domain | [Service boundaries](docs/architecture.md) |

Local application development uses the [development Playground](../docs/local-development.md).
