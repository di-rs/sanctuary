# Keep a Boxie slot for pull request reviews

Consider a team that wants to run its CI checks and Sanctuary's pull request
playground on one private Boxie host. A reviewer who opens a preview to try
the changed command needs one of the host's eight sandbox slots. If CI has
claimed all eight, Boxie turns away the request. An operator could reserve one
slot for review terminals. That would leave seven slots for batch jobs even
on an afternoon with no reviews.
[Using a playground preview](../../tools/cli-playground/README.md#use-a-preview)

## When a review has to wait

Two test clients each submitted four jobs concurrently to a local Boxie API.
Once all eight requests had replies, a third client requested a terminal.
The same trial ran against each policy with a fresh PostgreSQL database.
HTTP 202 records acceptance. Provisioning and opening the shell come afterward.

| Slot policy | Eight batch submissions | Reviewer's terminal request |
| --- | --- | --- |
| Current Boxie | All eight accepted | HTTP 429, capacity full |
| One slot reserved in a prototype | Seven accepted, one returned HTTP 429 | HTTP 202, accepted |

Sending the jobs one at a time also filled all eight slots under the current
policy. The test then recorded a successful result for the first job through
Boxie's completion code. After the submitting client read the exit code of
zero, the reviewer's request still returned 429. It succeeded once the
test supplied the supervisor's confirmation that the container was gone.
[Boxie admission and capacity](../../packages/boxie/docs/execution.md#admission-and-capacity)

## Where to set the limit

The operators of mybinder.org limit simultaneous sessions per repository to
keep one popular link from crowding out other users. They invite workshop
organizers who expect more than 100 users at once to request a higher quota.
Applying a cap per pipeline would take coordination on the Boxie host. An
allowance of four jobs apiece would still let two pipelines take all eight.
[Binder's policy for concurrent users](https://mybinder.readthedocs.io/en/latest/about/user-guidelines.html#maximum-concurrent-users-for-a-repository)

For a team using Buildkite, the first option to try is a shared concurrency
group. Pipelines in the same organization can put their batch steps in one
group limited to seven. Have each step submit one Boxie job and wait for its
result. A step that ends at HTTP 202 frees its Buildkite place while Boxie
still holds the slot. Even a step that waits for the result can finish before
cleanup. [Buildkite concurrency groups](https://buildkite.com/docs/pipelines/configure/workflows/controlling-concurrency#concurrency-groups)

The prototype changed how Boxie selects a free slot inside its existing
PostgreSQL transaction. A terminal request from the playground's authenticated
consumer took the reserved slot first and could use a general slot if that
one was occupied. All other requests competed for the seven general slots.
With six jobs already admitted, two more jobs and a terminal arrived together.
Boxie admitted the terminal and one job.

In a separate retry test, freeing the reserved slot still left a batch caller
with a 429. Once a general slot was free, its original submission key worked.
[Boxie job submissions and retries](../../packages/boxie/docs/consumer-api.md#submit-a-job-and-retrieve-its-result)

## Decide whether the slot is worth keeping

Ask two platform teams for the job arrival times from a release window when
batch work delayed a review. On each team's native Linux/gVisor test host,
replay ten bursts under its best existing CI concurrency settings and again
with the Boxie reservation. Open the preview when the eighth check becomes
ready in CI. Use the same retry schedule in each pair and include a pair with
delayed cleanup. [Boxie host requirements](../../packages/boxie/README.md#run-a-deployment)

Agree on the longest acceptable review wait and the batch deadline before
the trial. Time the reviewer's click until the browser shell returns `42`
for `echo $((6 * 7))`. Time each batch through its last result, including
retries. Try the reservation for a release if it meets the review target in
at least nine runs, finishes every batch by the deadline, and the team's
existing controls miss one of those targets.
