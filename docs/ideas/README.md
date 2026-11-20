# Choosing a Sanctuary pilot

To test demand for Boxie beyond the CLI playground, start with two teams
that self-host n8n and run an XML invoice validator on their own network.
A proposed n8n template would run the checker in Boxie, Sanctuary's
private sandbox runtime, and put the verdict in the team's existing
intake table. The question is whether recovering a lost reply would save
enough operator time to justify running another service.
[Proposed invoice validation pilot](n8n-invoice-validation.md)

For support engineers who receive a private CSV and cannot change its
export settings, compare the proposed browser picker with DuckDB's web
shell and a saved query. In a local trial, reusing a positional command
after the columns moved printed the requester's name. The pilot asks
whether checking headings automatically saves engineers time on each export.
[Private CSV preview pilot](browser-csv-preview.md)

## How n8n teams can run the validator

A team with a private validator host can use n8n's built-in SSH node to
upload the invoice and run the checker there. Include any delivery records
or retry handling the team already uses when comparing this workflow with
Boxie. [n8n SSH operations](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.ssh/)

A team running Windmill on its own infrastructure can call a script
asynchronously and choose the job ID before submission. If that ID already
belongs to a queued or completed job, Windmill rejects a duplicate
submission. A caller that loses the reply can poll for the result using
the ID it saved.
[Windmill self-hosting](https://www.windmill.dev/docs/advanced/self_host),
[script submission parameters](https://app.windmill.dev/tsdocs/types/RunScriptByHashData.html)
and [job lookup](https://www.windmill.dev/docs/core_concepts/webhooks#asynchronous-vs-synchronous)

Boxie assigns the job ID. If n8n loses Boxie's reply, it can repeat the
same request with its saved submission key and recover the original ID.
A supervisor restart poses a different problem. If Boxie authorized the
command to start and cannot confirm completion, it reports
`outcome_unknown`. The proposed workflow would mark that invoice
**Needs review**.
[Boxie job API](../../packages/boxie/docs/consumer-api.md#submit-a-job-and-retrieve-its-result)
and [recovery guarantees](../../packages/boxie/docs/execution.md#noninteractive-job-recovery)

## What would justify a second checker

Have each team try Boxie and the private runner it would otherwise use
with the same synthetic invoices. On both paths, test a valid invoice, a
schema mismatch and a missing schema. Then withhold the runner's reply
after it accepts a valid delivery and redeliver the original ZIP under
the same delivery ID. Count validator launches on the test host and
intake rows for that delivery. A single job ID can cover several launches
when Windmill is configured to restart a job whose worker stopped
reporting.
[Windmill worker recovery settings](https://www.windmill.dev/docs/core_concepts/environment_variables)

Time the hands-on work from redelivery to one correct intake row. Multiply
the difference in minutes by the team's count of comparable redeliveries
last quarter. Compare those potential savings with the extra time to set
up Boxie and the operator's estimate for a quarter of upkeep. A new
installation needs PostgreSQL, Temporal and a native Linux host with Docker
and gVisor.
[Boxie deployment requirements](../../packages/boxie/README.md#run-a-deployment)

If both teams meet the invoice pilot's timing and correctness targets,
show each operator the comparison. Try a second checker with a team that
expects to recoup the extra work within a quarter and brings the
validator it wants to run next. Keep the existing runner where it meets
the team's requirements with less work.

## Other pilots a team can try

| What a team can show you | Proposal |
| --- | --- |
| A missing image cost the operator another approved transfer into a disconnected network. | [Bring Boxie and a first job onto one Linux host](disconnected-boxie-trial.md) |
| A worker alert fires on a private Boxie host, and the support engineer can see only the ticket. | [Share the four worker checks from that host](worker-alert-handoff.md) |
| A private Boxie host passes its health check after a restore, and the operator needs to verify an earlier upload. | [Read the restored file from a new job](check-restored-upload.md) |
| An analyst needs to free a sandbox slot overnight and resume at the next candidate with their review flags intact. | [Pause a private Python review between shifts](pause-python-review.md) |
| CI checks fill a private Boxie host just as a reviewer opens a pull request preview. | [Keep one sandbox slot for review terminals](reserve-review-terminal.md) |
| A GitLab reviewer needs to try the Linux binary from a particular merge request build. | [Open that job's CLI in a private terminal](gitlab-cli-review.md) |
| A reviewer edited a failing input in the browser terminal and needs it again after the author pushes a fix. | [Keep the test file when switching CLI builds](keep-preview-input.md) |
| Two teams share a private sandbox host and need to explain their shares of its monthly bill. | [Split the fixed host cost by time reserved](shared-host-cost.md) |
| A reviewer needs to see a comparison a colleague has already set up in their browser terminal. | [Watch a teammate's running terminal](watch-running-preview.md) |
| A developer has a failed job's output and needs help interpreting it on their workstation. | [Explain selected lines with a local model](local-job-explanations.md) |
| Two warehouse importers pin different versions of the same library. Support needs to know which keeps the return reason. | [Compare the importers in private chat](open-webui-importer-versions.md) |
| A terminal assistant started suggesting the wrong commands after a model change. | [Compare local models against command fixtures](local-model-command-checks.md) |
| A maintainer's main and release checkouts use different targets to build the manual. | [Recall the build command for this checkout in Shish](shish-build-history.md) |
| An operator has a count of zero and needs to know whether the search read both depots' logs. | [Tell an empty search from an incomplete count in Shish](shish-search-exit-status.md) |
| A coding assistant changed a file while a developer had an unsaved edit open in Kara. | [Review both edits in the terminal](kara-assistant-edits.md) |
| Support engineers give different advice for two private builds with the same version number. | [Find the right manual for a CLI support ticket](build-specific-manual.md) |
| A Python CLI maintainer wants readers to copy an import command that fits their files and installed release. | [Build a Bash command in the tool's manual](click-command-in-docs.md) |
| A repackaged CLI still accepts a team's command but changes the IDs its script reads. | [Check a CLI rebuild against a downstream script](downstream-cli-rebuild.md) |
| A CI rerun is green, and a reviewer needs to know whether it ran the test that failed. | [Check the rerun with a local assistant](check-test-rerun.md) |
| A release engineer closed the editor during a test run and needs the failure for one build after another has finished. | [Reopen the private test run from an IDE assistant](reopen-test-run.md) |
| A JSON import works on a developer's laptop but runs out of memory on the team's smallest worker. | [Check the import against the worker's memory limit](import-memory-limit.md) |
| A release reviewer needs to know which proposed SQLite index preserves archived records in the team's staging database. | [Compare two migrations on one private snapshot](compare-sqlite-migrations.md) |
| An analyst can share row counts with support while the customer IDs must stay private. | [Reproduce a join with invented IDs](join-count-reproduction.md) |
| A mapping team needs to change a CSV import test after its Linux worker goes offline. | [Ship Biggie with the team's Pixi environment](offline-pixi-fixtures.md) |
| A fleet analyst can share charging totals in chat while driver IDs and site notes must stay on the laptop. | [Give a local assistant the totals from a charging export](charging-export-totals.md) |
| A reporter updated a notebook after a data correction, and the editor needs to check the number already in the story. | [Check a draft count against a fresh notebook run](notebook-story-count.md) |
| A book correction replaces the EPUB at the same filename before the first check finishes. | [Match an EPUBCheck verdict to the exact upload](epub-proof-versions.md) |
| A Kubernetes checksum check runs late, after the next newspaper index has arrived. | [Check the deposit for the intended issue date](kubernetes-deposit-check.md) |
| After a batch stops, an editor has to find which transcripts already contain corrections. | [Resume local transcription and preserve reviewed drafts](resume-interview-transcription.md) |
| A library migration touches a file a developer is still editing. | [Preview the migration in VS Code](editor-migration-preview.md) |
| A change reviewer received a dependency diagram for the wrong ticket revision. | [Download the diagram for the open revision](terraform-diagram-download.md) |
| A mentor repeats the same shell exercise for each new responder. | [Practice a runbook handoff in a private browser terminal](on-call-handoff-drill.md) |
| A screen-reader user needs to copy an earlier error while the command keeps printing. | [Read and search earlier terminal output](read-terminal-output.md) |
