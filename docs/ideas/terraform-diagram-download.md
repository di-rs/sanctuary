# Download a Terraform dependency diagram from a change ticket

Does the reporting job still depend on the catalog? Yesterday's diagram may
answer that question for the wrong revision of an infrastructure change.
A proposed **Download dependency diagram** action on the change ticket would
give the reviewer the image for the revision they have open, even after the
rendering job has finished.

## Where reviewers get diagrams today

HashiCorp's ServiceNow integration pauses an infrastructure request so an
approver can review the plan in HCP Terraform. For questions about
dependencies, `terraform graph` exports the relationships between a
configuration's resources as DOT, the text format Graphviz renders.
[ServiceNow approval workflow](https://developer.hashicorp.com/terraform/cloud-docs/integrations/service-now/service-catalog-terraform/service-catalog-config)
and [Terraform graph reference](https://developer.hashicorp.com/terraform/cli/commands/graph)

GitLab can display Graphviz diagrams through a self-hosted Kroki service.
GitHub Actions lets people with repository read access download a file from
a workflow run. The opening for Boxie is a private portal that already runs
sandboxed jobs and gives reviewers access to individual tickets. Attaching a
PNG directly from CI is the baseline for that team.
[GitLab's Kroki integration](https://docs.gitlab.com/administration/integration/kroki/)
and [GitHub Actions artifact downloads](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts)

## From a revision to its PNG

The team's build would run `terraform graph > graph.dot` in the initialized
checkout and send that file and the revision ID to the portal. The portal
would ZIP just the graph and submit a Boxie job. An operator would grant the
portal a profile with a pinned image containing Graphviz and fonts, a 1 MiB
limit shared by stdout and stderr, and one approved command. The command
writes the PNG to stdout.
[Boxie job profiles](../../packages/boxie/docs/configuration.md#choose-the-sandbox-image)
and [Graphviz output options](https://graphviz.org/doc/info/command.html)

```sh
/usr/bin/dot -Tpng /opt/artifact/graph.dot
```

The portal would save the job ID on that ticket revision and retire the input
ZIP after admission. Boxie recognizes the portal as one consumer, so the
portal's server would check the reviewer's access to the ticket on every
download. It would use its Boxie credential to fetch the result and decode
`stdout_base64`. A successful, untruncated result containing exactly one
complete PNG would yield `graph.png`. Seven days after confirmed cleanup,
the ticket would show **Diagram expired**. [Boxie job results](../../packages/boxie/docs/consumer-api.md#submit-a-job-and-retrieve-its-result)

## When a render produces a downloadable image

A local trial submitted a graph from Terraform 1.14.0 through Boxie's job
API. Graphviz 2.43.0 ran under Docker Desktop's `runc` runtime. The trial
invoked Boxie's lifecycle activity directly. After container removal, a fresh
client retrieved each result from PostgreSQL through the API. A second
consumer requesting the same result received HTTP 404.

| Input | Recorded result | What the portal would offer |
| --- | --- | --- |
| One dependency from `terraform_data.report` to `terraform_data.catalog` | Exit 0. All 4,235 bytes matched a direct Graphviz render. | Download the PNG. |
| Same graph, profile limit lowered to 1 KiB | Exit 0. Boxie retained the first 1,024 bytes and marked the result truncated. | Show that the render exceeded the output limit. |
| Two valid graphs in one file | Exit 0. Stdout contained two complete PNG images back to back. | Ask for a single graph. |
| Valid graph followed by a graph with a syntax error | Exit 1. Stdout still contained the complete first PNG. | Show the Graphviz diagnostic from stderr. |

The macOS image tool `sips` converted the two-graph result to the same bitmap
as the first graph alone. The portal would decode one image within a pixel
limit and check that its final chunk ends at the last byte of stdout.
[PNG end marker](https://www.w3.org/TR/png-3/#11IEND)

## Try it against the current attachment workflow

Pilot the profile under gVisor on one team's private Boxie host. Pick two
recent tickets where a dependency changed between revisions. Give each of
two reviewers one ticket with the team's usual attachments and one with the
proposed download. Swap tickets for the second reviewer so each ticket is
tried both ways. After reopening each revision, have the reviewer identify
the dependency. Record correct answers and the engineer's time spent
preparing or correcting attachments.

Try a second team if both reviewers identify the correct dependency on every
revision with the download, the portal denies a download to someone outside
the ticket, and the engineer spends less time per revision than with the
existing workflow. If CI already delivers the right image with no manual
work, keep the existing attachment.
