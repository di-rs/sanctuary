# Share a private Boxie worker alert with support

When a private Boxie installation raises `BoxieWorkerUnavailable`, the
on-site operator can inspect Temporal, the service Boxie's supervisor
polls for work. A support engineer outside the network may see only the
alert pasted into a ticket. A proposed local report would show the
engineer which queues had recent polls and which lookups failed.
[Boxie alert rules](../../packages/boxie/infra/observability/rules/boxie.yml)

A Temporal user shared startup logs from a healthy Kubernetes pod while
trying to find out why a workflow was waiting. The pod ran part of the
Temporal server. The application needed its own worker to poll its queue.
GitGuardian already lets self-hosted customers preview a support bundle
and transfer it from a disconnected installation.
[Temporal support exchange](https://community.temporal.io/t/how-do-i-set-the-taskqueue-name-of-a-worker/12456)
and [GitGuardian support bundles](https://docs.gitguardian.com/self-hosting/troubleshoot/support)

## What the responder would receive

Boxie uses one queue for the sandbox lifecycle and another for
maintenance. Each takes workflow tasks, which coordinate work, and
activity tasks, which carry it out. The operator would preview a file
containing the UTC capture time and four observations before attaching
it to the ticket. These four came from a local trial with Temporal
Server 1.32.2, mutual TLS and test workers.
[Boxie's worker configuration](../../packages/boxie/src/boxie/bootstrap/workers.py)

| Queue on the selected host | Workflow | Activity |
| --- | --- | --- |
| Sandbox lifecycle | Recent poll | Recent poll |
| Maintenance | Recent poll | No recent poll |

The maintenance activity worker was polling the queue named for another
host. Starting a worker on the intended queue changed the maintenance
activity result to **Recent poll**. It still read that way immediately
after the worker stopped. Boxie counts a poll less than 90 seconds old.
If work is still waiting, the responder can request another observation
after that window.
[Boxie's worker presence check](../../packages/boxie/src/boxie/bootstrap/dependencies.py)

In a second case the configured Temporal namespace did not exist. For
maintenance activities, Boxie's probe emitted the same values as in the
first case (`boxie_dependency_known=1`, `boxie_dependency_ready=0`).
After 31 seconds without a refresh on the test clock, the ready value
disappeared. A direct lookup returned `NOT_FOUND` for the missing
namespace. The report marked it **Lookup failed**, directing the
operator to check the configured namespace and connection.
[Boxie dependency probes](../../packages/boxie/src/boxie/observability/process.py)
and [metric freshness](../../packages/boxie/src/boxie/observability/metrics.py)

## What an operator can check today

Configure the Temporal CLI for the private server with the site's operator
certificate. Set `namespace` to Boxie's configured namespace (the default
is `boxie`) and `queue` to the full maintenance queue name. For the
example host `sandbox-1`, that name is
`boxie/<installation UUID>/sandbox-1/maintenance`. Use the installation
ID from the host's API configuration.
[Boxie API configuration](../../packages/boxie/docs/configuration.md#start-the-api)
and [queue names](../../packages/boxie/src/boxie/temporal/contracts.py)

```sh
temporal task-queue describe --namespace "$namespace" \
  --task-queue "$queue" --task-queue-type activity
```

The CLI exited zero both for an empty poller list and for one containing
the test worker's identity. Read the rows under **Pollers** for the last
time each worker requested an activity. Omitting
`--task-queue-type` includes all types, so an operator can describe the
two queues and copy the observations by hand. Boxie queue names contain
the installation and host identifiers. Temporal's default worker identity
includes the process ID and hostname.
[Temporal queue inspection](https://docs.temporal.io/cli/command-reference/task-queue#describe)
and [worker identities](https://docs.temporal.io/workers#worker-identity)

The proposed Python collector would derive both names from the host's
Boxie configuration and use the Temporal SDK's `DescribeTaskQueue` call
with a four-second timeout per lookup. The trial's JSON contained only
the capture time, fixed queue and task labels, and their results. The
operator's certificate stays on the host. Sites using Replicated
Troubleshoot could add this file to an existing support bundle with its
host file collector.
[Boxie private transport](../../packages/boxie/docs/temporal.md#trust-and-private-transport)
and [Troubleshoot's file collector](https://troubleshoot.sh/docs/host-collect-analyze/copy/)

## Decide whether to ship the collector

Recruit two teams that have had to request more evidence from a private
host. Pair each operator with a responder who can see only the ticket.
Give each pair matched cases of a worker polling the wrong queue, a
failed lookup and a control with all four roles polling. Compare the
report with the team's usual handoff, including any saved Grafana
queries or CLI scripts. Reverse the order for the second pair.

Score the first reply on whether it identifies the affected queue and
task type, asks to verify a failed lookup, or reports four recent polls
as appropriate. Count follow-up questions and hands-on minutes on both
sides, including setup and review. Package the collector if both pairs
interpret every case correctly, share only the agreed fields and each
save at least one round of questions within their usual handoff time.
