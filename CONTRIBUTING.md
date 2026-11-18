# Contributing to Sanctuary

Sanctuary currently accepts changes from its maintainers only. Maintainers can
follow the [CLI development guide](docs/cli-development.md) to add a command,
run local checks and publish browser recordings with the pull request.

Use the [default-branch merge policy runbook](docs/merge-policy.md) to resolve
drift reported during maintenance or verify changes to required checks.

For production database and schema changes, complete the **Risk Assessment** in
the PR description, including on Dependabot PRs. Describe the effect on the deployed
cluster, the evidence from existing data, and how an operator can recover. Reviewers
verify that evidence before resolving upgrade warnings. See [PostgreSQL data
preservation](packages/boxie/docs/database.md#preserve-data).
