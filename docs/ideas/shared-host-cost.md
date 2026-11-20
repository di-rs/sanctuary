# Explain the fixed cost of a shared Boxie host

A platform engineer has one monthly bill for the machine that runs CI checks
and release previews. At the budget review, each team wants to know its share.
A proposed CSV from Boxie, Sanctuary's sandbox runtime, would show how long
each team's apps held slots and their share of the rental. Unreserved slots
would have a separate line in the platform budget.

A GitHub Codespaces user who could see costs by machine type asked for a
breakdown by user or repository. After trying GitHub's usage export, they
asked to see the figures on the Insights page. GitHub cost centers can
attribute Codespaces usage by repository or organization.
[Customer request and GitHub's reply](https://github.com/orgs/community/discussions/9611)
and [Codespaces cost allocation](https://docs.github.com/en/billing/reference/cost-center-allocation)

OpenCost gives Kubernetes operators a choice about distributing the cost of
idle capacity among tenants. For a private Boxie trial, use a dedicated host
at a fixed rental rate and leave the unreserved share in the platform budget.
Even during downtime, the host rental continues.
[OpenCost allocation model](https://opencost.io/docs/specification/#shared-costs)

## One terminal and three CI checks

A sandbox reserves one of the host's eight slots from admission until Boxie
records confirmed removal in PostgreSQL. A quiet terminal and a busy command
each account for one slot-minute every minute they hold a slot.
[Boxie admission and cleanup](../../packages/boxie/docs/execution.md#admission-and-capacity)

A local PostgreSQL trial used Boxie's admission and cleanup code with synthetic
times. Two CI jobs held slots from 00:01 to 00:04 and 00:02 to 00:05 UTC.
Retrying the first submission returned the same job ID. A third job held its
slot from 00:54 to 01:05. One release terminal crossed midnight, from 23:54
to 00:30. For the hour beginning at midnight, the eight slots provided 480
slot-minutes. At an illustrative $0.80 for that hour, each owner's share is
its fraction of those minutes multiplied by $0.80.

| Owner | Slot-minutes in the hour | Share of host rental |
| --- | ---: | ---: |
| CI | 12 | $0.02 |
| Release reviews | 30 | $0.05 |
| Platform (unreserved) | 438 | $0.73 |
| Whole host | 480 | $0.80 |

The third job already had a successful result when the query first ran with
its slot still reserved. Recording its removal at 01:05 kept the first hour
at 12 CI minutes and put five in the next hour.

## From seven days of records to a monthly CSV

Boxie's Grafana capacity panel shows how many slots are reserved across the
host. For ownership, query the lifecycle rows using the authenticated app's
`consumer_id`. Have the operator record which team owns each ID for the period.
An ID used by both teams would appear as shared.
[Boxie capacity dashboard](../../packages/boxie/infra/observability/grafana/dashboards/boxie.json)
and [consumer identities](../../packages/boxie/docs/configuration.md#consumer-credentials-and-transport)

Run the query for a completed period whose start is still within the
retention window. Bind the UTC start and end times, installation UUID and
host ID through Psycopg. The operator needs read access to five columns.

```sql
WITH period AS (
    SELECT %(start_utc)s::timestamptz AS starts_at,
           %(end_utc)s::timestamptz AS ends_at
)
SELECT consumer_id,
       sum(least(coalesce(cleaned_at, ends_at), ends_at)
           - greatest(accepted_at, starts_at)) AS reserved_time
FROM sandboxes CROSS JOIN period
WHERE installation_id = %(installation_id)s AND host_id = %(host_id)s
  AND accepted_at < ends_at AND (cleaned_at IS NULL OR cleaned_at > starts_at)
GROUP BY consumer_id
ORDER BY consumer_id;
```

Seven days after confirmed cleanup, Boxie can delete a sandbox's timing
records. After the test aged the four sandboxes and ran the retention sweep,
all three successful job receipts survived. The query returned no rows for
the same hour. Calling that hour unreserved would put the entire $0.80 in
the platform budget. [Boxie retention and ownership](../../packages/boxie/docs/database.md#retention-and-ownership)

Close each UTC day after admission and cleanup writes spanning midnight
settle. A local SQLite prototype replaced a host's daily totals and its
completion record in one transaction. Saving a day twice counted it once.
After the source rows expired, the prototype distinguished a recorded day
with zero reservations from a missing day. The monthly export would sum
durations before applying the host rate. If a missed day has aged beyond
recovery, label the month **Incomplete** and name the missing date.

## Try it at a monthly budget review

Recruit two platform teams that already split a fixed host bill among app
owners. For one billing cycle, let each team prepare the statement with its
usual spreadsheet or SQL process and the proposed export. Give both methods
the same host rate, owner mapping and access to records while they are fresh.
Check accuracy against a known schedule with a midnight crossing, a repeated
submission and delayed cleanup. Remove one daily record from an expired
period in a test copy.

Count hands-on minutes for setup, reconciliation and explaining the split to
the app owners. Package the export if both teams reproduce the scheduled
slot time for every owner, flag the missing date, and cut that first month's
preparation time by at least half against their usual method.
