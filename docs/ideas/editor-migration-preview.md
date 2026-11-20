# Review a private code migration in VS Code

A library team ships a script for migrating callers to its next release. A
developer wants to try it on a file that already contains uncommitted work.
With a proposed **Preview migration** action in VS Code, the developer could
send that file to the team's private Boxie installation, see which lines the
script would change and decide whether to apply the edit.

Workiva's platform team had to carry package updates across at least 70
repositories. It used Sourcegraph Batch Changes to update UI component syntax
for a new Dart version. OpenRewrite's Maven plugin lets maintainers inspect a
migration as a patch. Sanctuary could test demand for a one-file preview among
teams that want to maintain their migration tools on one host and give the
service access only to the file a developer selects.
[Sourcegraph's Workiva case study](https://sourcegraph.com/case-studies/workiva-automates-large-scale-code-changes)
and [OpenRewrite dry runs](https://docs.openrewrite.org/reference/rewrite-maven-plugin)

## Try a one-file migration

Ruff already offers quick fixes in VS Code. Its deprecated-import rule gives
the pilot a public example to try before packaging a private rule. With
Python 3.11 as the target, the preview for this `input.py` would move the
`Mapping` import to `collections.abc`.
[Ruff editor actions](https://docs.astral.sh/ruff/editors/features/)
and [the deprecated-import rule](https://docs.astral.sh/ruff/rules/deprecated-import/)

```python
from collections import Mapping


def invoice_total(row: Mapping) -> int:
    return row["total"]
```

The extension would keep a snapshot of the open document and its version. A
team service would authenticate the developer, upload the UTF-8 text in a ZIP
as `input.py` and submit a Boxie job. It would hold the Boxie credential,
return results only to the submitting developer and retire the input after
admission. The job result can contain the whole revised file and stays
readable for seven days after confirmed cleanup.
[Boxie job and artifact API](../../packages/boxie/docs/consumer-api.md#submit-a-job-and-retrieve-its-result)

An operator would grant the service a profile with a digest-pinned image and a
fixed command. A wrapper in that image would feed `/opt/artifact/input.py` to
Ruff. With Ruff installed, the equivalent local command reads `input.py` and
writes the revised source to stdout.

```sh
ruff check --isolated --no-cache --target-version py311 --select UP035 \
  --fix --stdin-filename input.py - < input.py
```

In Ruff 0.17.5, using `--quiet --diff` in place of `--fix` produced empty
output and exit code zero for both an up-to-date file and an unfinished
import. The command above returned the current file for the first case and
exited 1 with a syntax diagnostic for the second.

## When an edit is ready to apply

The extension would take replacement text only from valid UTF-8 stdout for a
`succeeded` job with `truncated=false`. A match with the snapshot would show
**No changes**. If the text differs, the extension could open both versions
as read-only virtual documents in VS Code's diff editor. **Apply** would
update the original document with a version-checked edit. If the developer
had edited it since submission, the extension would offer **Preview again**.
A failed job would show its diagnostic, and an incomplete or expired result
would show its status.
[VS Code virtual documents](https://code.visualstudio.com/api/extension-guides/virtual-documents)
and [the diff command](https://code.visualstudio.com/api/references/commands)

Ruff returned 102 bytes for the example above. In a local trial, Boxie's
capture reader received stdout first in simulated Docker frames. With a
36-byte output limit it kept only the import, with exit code zero and
`truncated=true`. Python parsed that single line, and `git apply --check`
accepted a diff that would have deleted `invoice_total`.
[Boxie capture tests](../../packages/boxie/tests/test_job_capture.py)

## Pilot with a library team

Ask one library owner for a real one-file migration and expected edits for two
similar call sites. Give three downstream developers one site to migrate with
the team's current instructions and one with the preview. Alternate which
method they try first. Measure time from receiving the file to producing the
expected edit, including setup of the local tools or extension. Record the
owner's time to package the rule separately. Repeat with a truncated result
and with a developer typing during review. Try a second migration if both
cases preserve the developer's work, all three developers produce the
expected edits on complete results and at least two finish sooner with the
preview.
