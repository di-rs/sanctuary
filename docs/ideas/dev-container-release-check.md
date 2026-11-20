# Bring a Dev Container's Python release check to Boxie

A Python SDK team rejects releases that use a deprecated API. Its private
release service could submit that check to Boxie, Sanctuary's sandbox
runtime, and collect the verdict by job ID. Before switching, the release
engineer needs to know whether Boxie will reject the same revisions as the
team's Dev Container in CI. A proposed local Sanctuary CLI would compare a
known good revision and a known bad one on both runners.

Teams can already build a Dev Container image and run their checks in it on
GitHub Actions or Azure DevOps with `devcontainers/ci`. One user comparing
startup in VS Code and CI found that the CI launch omitted compiler settings
such as `CC=gcc` that their shell initialization scripts expected.
[Dev Container CI integration](https://github.com/devcontainers/ci#quick-start)
and [compiler environment report](https://github.com/devcontainers/ci/issues/394)

## How a deprecated call passed the check

In a local trial, Dev Container CLI 0.91.0 built a Python 3.12.16 image with
`PYTHONWARNINGS=error::DeprecationWarning` in its `remoteEnv` settings.
The CLI stored the setting in the image's `devcontainer.metadata` label.
A Dev Container client applies those settings when it launches a task.
The SDK checkout referenced that prebuilt image. With the image available
locally, this command returned `{"checkout":[],"merged":["PYTHONWARNINGS"]}`.
[Dev Container image metadata](https://github.com/devcontainers/spec/blob/main/docs/specs/devcontainer-reference.md#merge-logic)

```sh
devcontainer read-configuration --workspace-folder . --include-merged-configuration |
  jq -c '{checkout: (.configuration.remoteEnv // {} | keys),
          merged: (.mergedConfiguration.remoteEnv // {} | keys)}'
```

The release command was `/usr/local/bin/python /opt/artifact/check.py`.
The script imported `stamp` from a neighboring `release_clock.py` and called
it. That module imported `UTC` and `datetime` from Python's `datetime`
library. The two fixtures differed only in which expression `stamp()`
returned. All six runs used the same image digest.

| Launch | `datetime.now(UTC)` | `datetime.utcnow()` |
| --- | --- | --- |
| `devcontainer exec` | Exit 0 | Exit 1, `DeprecationWarning` |
| Boxie job command | Exit 0 | Exit 0, empty stderr |
| Boxie job command with `-W error::DeprecationWarning` before the script path | Exit 0 | Exit 1, `DeprecationWarning` |

Python normally suppresses deprecation warnings from imported modules.
Boxie launched Python with the image's environment, so the deprecated call
returned silently. An operator can make the rule explicit in the job
profile's approved arguments. The two Boxie rows used its job container
configuration and output capture with `runc` on Docker Desktop.
[Python warning filters](https://docs.python.org/3.12/library/warnings.html#default-warning-filter),
[Boxie job profiles](../../packages/boxie/docs/configuration.md#choose-the-sandbox-image)
and [the local job test setup](../../packages/boxie/tests/test_job_capture.py)

## Try it during a profile review

Start with a team that already operates Boxie and has two checks it wants to
move. For each, ask the maintainer for a passing revision, a rejected
revision and the diagnostic CI gives for the rejection. On a private Linux
staging host with gVisor, the operator would pin the same image and grant
the team a profile with the candidate commands. The release service would
record each revision with its CI verdict and Boxie job ID. Given those
records and the checkout, the local CLI would retrieve the staging results
and show the exit codes and diagnostics beside the merged `remoteEnv`
names. An unexpected diagnostic, truncated output or an unknown job outcome
would leave the check open for review.
[Boxie job results](../../packages/boxie/docs/consumer-api.md#submit-a-job-and-retrieve-its-result)

For each check, prepare two candidate commands. One preserves the release
rule and one omits it. Have two engineers each choose which command to
approve. Give one the CLI for the first check and the other the CLI for the
second. For their manual reviews, give them the same fixtures, metadata
command and job results. Try a second team if both engineers catch every
false pass and the CLI shortens review time on both checks. If the manual
review works as well, keep the fixtures with the release service.
