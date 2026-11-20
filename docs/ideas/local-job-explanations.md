# Explain a failed Boxie job with a local model

A developer on call for an application that uses Boxie, Sanctuary's sandbox
runtime, may have just a job ID when a customer reports a failure. A proposed
terminal viewer would let the developer open the result their application
exports, select lines, and ask a model on their workstation what to inspect next.

Consider a job that counts bytes in an uploaded file. It exits with code 1, and
the first line of stderr says that `wc` could not open `/opt/artifact/input.txt`.
Choosing **Explain locally** for that line could yield the suggestion “Check
whether `input.txt` is at the top level of the uploaded ZIP (stderr, line 1).”

## What developers can use today

GitHub Actions offers **Explain error** from a failed check or workflow summary.
GitLab Duo can analyze the final 100,000 characters of a failed CI job log and
supports self-hosted models. An app using Boxie could borrow that placement by
offering the result export where it reports a failed job.
[GitHub Actions troubleshooting](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows#using-github-copilot)
and [GitLab Duo job troubleshooting](https://docs.gitlab.com/user/gitlab_duo_chat/examples/#troubleshoot-failed-cicd-jobs-with-root-cause-analysis)

For jobs submitted outside CI, the `llm` CLI already accepts piped output and
supports local models through plugins. It logs prompts and responses to SQLite
by default and lets the user disable logging. A Boxie viewer could put each
suggestion beside the recorded job state and the lines that support it,
including whether the capture is complete.
[LLM prompt usage](https://llm.datasette.io/en/stable/usage.html#executing-a-prompt)
and [logging behavior](https://llm.datasette.io/en/stable/logging.html)

## From the submitting app to the workstation

The viewer would read one job record from standard input. For a live
integration, the submitting app would check the developer's access to that
specific job before exporting it. The app's server would keep its Boxie
credential and use it to read `GET /v1/jobs/{id}` and, for a `failed` job,
`GET /v1/jobs/{id}/result`. [Boxie job API and byte-count example](../../packages/boxie/docs/consumer-api.md#submit-a-job-and-retrieve-its-result)

For a recorded failure, show the exit code and number the decoded stdout and
stderr lines within each stream. Escape control characters and non-text bytes
before displaying them. Boxie keeps the first bytes it reads across both streams up
to a shared limit. When `truncated` is true, mark the output as incomplete
because the last error line may be missing. If the result has expired, show
the recorded state with “Output expired.”

A supervisor can lose a result after the command starts. For `outcome_unknown`,
the viewer would show Boxie's recovery advice directly. Confirm cleanup with
the operator and check for effects before submitting a fresh job, since a
second run could repeat work. [Boxie recovery guarantees](../../packages/boxie/docs/execution.md#noninteractive-job-recovery)

For the prototype, start Ollama on the workstation's loopback interface with
a model installed in advance and `OLLAMA_NO_CLOUD=1`. Send the selected lines,
labeled by stream and line number. Ask for a possible cause, a next inspection
step, and references to those lines using Ollama's JSON schema support. The
viewer would keep excerpts and replies in memory, check that the cited lines
exist, and render the suggestion as plain text. If the model is unavailable or
cites a missing line, show the original output with the reason.
[Ollama local configuration](https://docs.ollama.com/faq) and
[structured outputs](https://docs.ollama.com/capabilities/structured-outputs)

## Test whether explanations shorten diagnosis

Give four application developers eight synthetic job records, including a
missing input, a truncated diagnostic, an expired result, and an unknown
outcome. Let each developer see each case once. Rotate which cases offer
explanations so each case is also tried with the plain viewer. Score each
developer's first decision against an answer key. Measure time from opening
the record, including model startup. Take the idea to a live pilot if the
model cuts median time to a correct decision by at least 20%, developers make
at least as many correct decisions, and everyone checks for prior effects
before suggesting a retry on a job with an unknown outcome.
