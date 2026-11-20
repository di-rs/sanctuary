# Reopen a private test run from an IDE assistant

A release engineer starts the export tests for build 42 and closes the
editor. A proposed Model Context Protocol (MCP) tool would run the suite
in Boxie, Sanctuary's private sandbox service. The engineer could open a
fresh chat the next morning, ask which test failed on build 42 and get
back **Build 42, attempt 1 failed `test_part_number`**, even if another
build finished overnight.

A developer using GitHub Copilot in JetBrains Rider reported that a
ten-minute coverage run outlasted the assistant's tool call. For teams
that keep the editor open, the maintainer suggested raising the
per-server timeout available since plugin version 1.15.0.
[Developer report and maintainer's resolution](https://github.com/microsoft/copilot-intellij-feedback/issues/1935)

## Which build lost the leading zeros?

In a local Boxie trial, two CSV files stood in for exports from successive
builds. The same Python `unittest` suite checked each file for the heading
`part_number` and first value `007`. The trial held build 41's check
open until build 42's finished.

| Build | Heading | First value | Finished | Failing test |
| --- | --- | --- | --- | --- |
| 41 | `component` | `007` | Second | `test_header` |
| 42 | `part_number` | `7` | First | `test_part_number` |

The MCP client and its tool server closed after each submission. A fresh
client saw build 41 still running. After both checks exited 1, looking
up build 42's saved job ID returned `test_part_number`.
Taking the last run to finish as the answer for build 42 would have sent
the engineer to fix the header. The trial used short synthetic checks,
Docker Desktop's `runc` runtime and Boxie's Temporal test server.

An operator can retrieve the same assertion failure today with Bash,
curl and jq. On the private consumer host, set `BOXIE_URL` to the API
base URL, `BOXIE_TOKEN` to the consumer secret and `JOB_ID` to the ID
saved for that build. This prints the `FAIL` lines from an untruncated
`unittest` report with exit code 1.

```bash
set -o pipefail
curl -fsS -H "Authorization: Bearer $BOXIE_TOKEN" \
  "$BOXIE_URL/v1/jobs/$JOB_ID/result" |
  jq -er 'select(.exit_code == 1 and .truncated == false)
    | .stderr_base64 | @base64d | split("\n")[]
    | select(startswith("FAIL: "))'
```

## How a fresh chat would find the run

Give each pilot engineer a private adapter with one Boxie consumer
credential and a grant for the test profile. **Start export check** would
look up the build's uploaded artifact and the approved test command.
Before submitting, it would save the exact request and its submission key
in SQLite on the adapter host, indexed by project, build and attempt.
It would add the job ID when Boxie replies. **Read export check** would
use that ID to return the run state and, when available, the failing
test names. If a build has several attempts, the engineer would choose
one. The credential would stay on the adapter host.

In the trial, dropping the saved job ID for build 42 and repeating its
request with the original key recovered the same ID. The suite recorded
two launches in total. Moving the recorded cleanup time eight days into
the past put the result outside Boxie's seven-day retention window. The
job state still read `failed` and the output request returned HTTP 410.
The adapter could show **Run failed (report expired)**.
For `outcome_unknown`, it would show **Completion unconfirmed** and leave
a new attempt to the engineer.
[Boxie job recovery and result retention](../../packages/boxie/docs/consumer-api.md#submit-a-job-and-retrieve-its-result)

The two ordinary tool calls worked over standard input and output. With
support for the July 2026 MCP Tasks extension in both the IDE and the
adapter, the IDE could save a task ID and poll `tasks/get` itself.
When the suite fails and the adapter delivers its report, the task status
is `completed` and the result contains the test verdict. The extension's
schema rejected a reply that copied Boxie's `failed` state onto the task
and attached the same result. That status requires a protocol error.
[MCP Tasks specification](https://github.com/modelcontextprotocol/ext-tasks/blob/main/specification/2026-07-28/tasks.md#task-execution-errors)

## Would engineers use it after closing the editor?

Recruit two release teams that already operate a private Boxie host and
have an offline Linux suite that engineers leave running when they close
their editors. Compare the adapter with each team's saved CI run links.
A team using self-hosted Windmill can also return a flow's run ID early
and expose a second tool to read its status. Use that workflow where it
is the team's usual route. Give both routes the same build and attempt
labels.
[Windmill's MCP tools](https://www.windmill.dev/docs/core_concepts/mcp#access-levels)

Have four engineers try both routes, running the Boxie checks under
gVisor on native Linux. Alternate the order and swap build pairs between
engineers so each sees fresh failures on their second route. Close the
editor after submission, let two builds finish out of order and ask for
the failing test on each. Include a run whose output has expired. Time
from reopening the editor to the correct answer and count suite launches.
Try a second suite if all four identify every available failure and the
expired report, each requested check runs once, and at least three
engineers cut their median lookup time by a minute.
