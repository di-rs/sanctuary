# Try a Linux CLI from its GitLab merge request

GitLab CLI merge request !4276 restored a missing list of environment
variables in `glab api --help`. Its author checked the output of builds
before and after the fix. A technical writer reviewing a Linux CLI from
a Mac could select **View app** in a self-managed GitLab project, try
the command in a private Sanctuary terminal and cite the build job
alongside its output.
[GitLab CLI help change](https://gitlab.com/gitlab-org/cli/-/merge_requests/4276)
and [GitLab Review Apps](https://docs.gitlab.com/ci/review_apps/#view-review-apps)

## Which commit would the terminal run?

A merge train tests a change together with changes ahead of it in the
queue. For the help change, the source branch ended at `35dd591b` and the
successful train ran `651c4943`. To see the source commit, tested commit
and pipeline ref, run this public query with curl and jq.
[Merge request record](https://gitlab.com/api/v4/projects/34675721/merge_requests/4276)
and [how merge trains work](https://docs.gitlab.com/ci/pipelines/merge_trains/)

```sh
curl -fsSL 'https://gitlab.com/api/v4/projects/34675721/merge_requests/4276' |
  jq -r '[.sha[:8], .head_pipeline.sha[:8], .head_pipeline.ref] | @tsv'
```

The proposed terminal would label that build **Merge train 651c4943 ·
job 17759726517**. Retrying a job gives it a new ID and can produce
different binaries at the same commit.
[Build job for the help fix](https://gitlab.com/gitlab-org/cli/-/jobs/17759726517)
and [GitLab job retries](https://docs.gitlab.com/ci/jobs/#retry-jobs)

## Connect one private project

Today's playground publishes builds from GitHub and identifies previews
by pull request number. Two GitLab projects can both have a merge request
!123, so give the pilot project its own gateway and database. Its build
job would put the merge request number and job ID in the Review App URL
using GitLab's dotenv report.
[Playground preview identity](../../tools/cli-playground/src/cli_playground/domain.py),
[current publisher](../../tools/cli-playground/docs/previews.md)
and [GitLab dynamic environment URLs](https://docs.gitlab.com/ci/environments/#set-a-dynamic-environment-url)

On opening the link, the reviewer would sign in with GitLab. The
playground page, API and terminal WebSocket would require permission to
read the open merge request and download the selected job's artifact.
A publisher on the team's network would look up the configured build job
in the merge request's current pipeline. If that job succeeded and its
ID matches the link, the publisher would fetch the Linux executable by
job ID, put it in a flat ZIP and publish it with its own deployment token.
Boxie would run the binary when the reviewer starts a terminal.
[GitLab pipeline jobs](https://docs.gitlab.com/api/jobs/#list-all-jobs-by-pipeline),
[single-file artifact downloads](https://docs.gitlab.com/api/job_artifacts/#download-a-single-artifact-file-by-job-id)
and [playground execution](../../tools/cli-playground/docs/architecture.md#from-pull-request-to-terminal)

A later GitLab CLI job produced an 887 MiB archive, above the
playground's 512 MiB limit. Fetching just its Linux x86-64 executable
brought the input down to 52.6 MiB. In a local test with PostgreSQL, the
gateway accepted the file as the sole ZIP entry, `glab`. The downloaded
executable and the copy delivered to a Boxie test double had the same
SHA-256 digest.
[Build job](https://gitlab.com/gitlab-org/cli/-/jobs/18201323574)
and [playground upload limits](../../tools/cli-playground/src/cli_playground/artifacts.py)

The gateway also admitted a new session for the previous build after a
newer build failed. Two successful attempts at the same commit shared a
preview URL. After the retry, a new session for the old revision returned
HTTP 409. The GitLab link would therefore request the revision formed
from the tested commit, pipeline number and producing job ID. A failed,
expired or superseded build would show its status and a link to its job.

## When would the browser save time?

Recruit one team with a private Boxie host and a CLI that runs offline.
Have two reviewers try comparable changes using GitLab's artifact
download on their usual Linux setup and **View app** on the team's
gVisor host. Swap methods for a second pair. Include a failed build and
a retry. Count a review as correct when it names the job and reproduces
the expected output or explains why that build is unavailable.
[GitLab artifact links in merge requests](https://docs.gitlab.com/ci/yaml/#artifactsexpose_as)

Verify that a colleague who lacks artifact access gets **Access denied**
from a copied link. Time each review from opening the merge request to
recording the result. Add a second project if every review is correct
and the time saved at the team's monthly review volume covers setup
spread over three months plus monthly upkeep.
