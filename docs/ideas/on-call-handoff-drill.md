# Practice an on-call handoff in the browser

A support lead could add a **Practice this handoff** link beside the
log-collection step in the team's private runbook. Before their first shift,
a responder would open a Bash terminal in the browser, extract error records
from a synthetic log and check the file they would hand to a teammate.

A Google SRE team rehearsed recent incidents and ran debugging labs while
preparing for its first on-call rotation. Datadog's customer education team
reports that software installation requirements got in the way at workshops.
It now uses Instruqt browser labs in its self-paced courses. Sanctuary could
offer that format to teams that already operate Boxie and want to maintain
their own exercises.
[Google's on-call case study](https://sre.google/workbook/on-call/)
and [Datadog's account of using Instruqt](https://instruqt.com/customer-stories/datadog-2)

## What counts as a correct handoff

The learner's task is to save every record whose severity is `ERROR` to
`errors.txt`, preserving the original lines in order. In the sandbox's sample
log, searching for `ERROR` anywhere on a line finds the one error. In the
second log, `next-shift.log`, an informational message also mentions `ERROR`.
[Sanctuary's sample log](../../packages/boxie/sandbox/fixtures/app.log)

```text
2026-01-02T10:00:00Z ERROR queue stalled
2026-01-02T10:00:01Z INFO previous ERROR cleared
2026-01-02T10:00:02Z ERROR retry exhausted
```

The responder could run these commands from the sandbox workspace.

```sh
grepr '^[^ ]+ ERROR ' /opt/artifact/next-shift.log > errors.txt
check-handoff
```

The proposed `check-handoff` script would compare the checksum of `errors.txt`
with the runbook owner's expected SHA-256. In a local trial, both the
`grepr` command above and `awk '$2 == "ERROR"'` produced the two expected
lines and received **Ready for handoff**. Searching for `ERROR` anywhere
returned all three lines. Searching for `^ERROR` returned none. Both searches
exited successfully, and the checker prompted the learner to check the
severity after the timestamp.
[grepr matching behavior](../../buildins/grepr/README.md#before-using-it)

## Deliver a drill from the runbook

The runbook owner would review a ZIP containing both logs, a Linux build of
`grepr`, the checker and its answer checksum. In a local check, the
playground's PR bundle validator rejected the log filename. It expects Linux
executables with an optional command catalog. Boxie's ZIP extractor accepted
the exercise files together. A training service could upload each reviewed ZIP
through Boxie's private artifact API and pin its ID in the runbook revision.
[Preview publication](../../tools/cli-playground/docs/previews.md#build-and-comparison-contract)
and [Boxie artifacts](../../packages/boxie/docs/execution.md#artifacts)

The service would use the team's sign-in, keep the Boxie credential on the
server and give each learner access to their own sandbox through the browser
terminal. Boxie mounts the artifact read-only and disables sandbox networking.
If a session expires, reopening the drill would start a clean workspace with
the same exercise.
[Boxie terminal API](../../packages/boxie/docs/consumer-api.md#manage-artifacts-and-sandboxes)

## Try it with one on-call rotation

Give three new responders the current runbook and sample files for local use.
Give three others the same instructions and the browser drill. After practice,
give everyone a fresh log to investigate unaided. Have a mentor check the
handoff files against the same answer key. Record mentor minutes spent helping
each group during practice and the owner's time to prepare the drill.

Try a second procedure if all three browser learners produce a correct unaided
handoff and the mentor time saved per learner would repay the preparation time
over the team's next onboarding cohort.
