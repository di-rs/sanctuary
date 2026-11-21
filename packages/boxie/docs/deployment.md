# Deploy Boxie

Run **Deploy Boxie** from GitHub Actions to release the private API, supervisor and sandbox image. The workflow builds these from the protected branch and publishes them to private object storage. For the first installation, start PostgreSQL and Temporal before deploying Boxie. [First deployment](../../../infra/docs/setup.md) · [Release operations](../../../infra/docs/releases.md)

The supervisor owns Docker and the gVisor sandbox data directory. The API owns consumer authentication. Each process has a separately mounted Temporal identity. The application receives database credentials, Temporal connection settings and the OTLP endpoint through its deployment configuration. [Service boundaries](../../../infra/docs/architecture.md)

## Configure a disposable native Linux host

The native suite requires Linux amd64, Docker Compose and a registered `runsc` runtime. **Boxie lifecycle integration** in GitHub Actions prepares a disposable runner. Its workflow-dispatch run exercises a native sandbox, lifecycle recovery and cleanup. **Sanctuary browser integration** also checks the Playground against Boxie. [Boxie tests](../../../.github/workflows/boxie-lifecycle.yml) · [Browser integration](../../../.github/workflows/sanctuary-lifecycle.yml)
