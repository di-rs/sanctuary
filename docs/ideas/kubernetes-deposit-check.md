# Check the intended archive deposit after a late Kubernetes run

A newspaper archive receives a text index for each issue. By the time an
operator retries the November 18 checksum check, the November 19 index has
also arrived. A script that opens today's file can report success while
the damaged November 18 delivery goes unnoticed. A proposed Kubernetes
CronJob template would ask Boxie, Sanctuary's private sandbox runtime, to
check the index for the intended date. If the submitting Pod disappears,
its replacement could retrieve the hash and finish recording the verdict
in the archive's intake table.

The Digital Preservation Coalition recommends comparing incoming files
with the checksums the depositor recorded before transfer. Archivematica
checks packages in its storage service and shows the date and outcome for
each package. The proposed template serves an earlier decision at intake,
when the archivist can still ask the depositor for a replacement.
[Digital Preservation Coalition acquisition guide](https://www.dpconline.org/handbook/organisational-activities/acquisition-and-appraisal)
and [Archivematica's Fixity checker](https://github.com/artefactual/fixity#check-fixity)

## Find the date the scheduler requested

In a Kubernetes issue, a maintainer changed a CronJob schedule and saw a
new Job marked for the previous day. From version 1.32, the CronJob
controller records the intended start time on the Job it creates. For an
archive that schedules one check per issue date in UTC, that timestamp
identifies which delivery to look up.
[Maintainer's observation](https://github.com/kubernetes/kubernetes/issues/128155#issuecomment-2428693016)
and [Kubernetes CronJob scheduling](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/#job-creation)

With `kubectl` and `jq`, set `NS` to the intake namespace and `JOB` to
the name of a Job scheduled by a CronJob named `deposits`. Inspect its
timestamp and preview the annotations a manual run would receive.

```sh
kubectl -n "$NS" get job "$JOB" -o json |
  jq -r '.metadata.annotations["batch.kubernetes.io/cronjob-scheduled-timestamp"]'
kubectl -n "$NS" create job deposit-retry --from=cronjob/deposits --dry-run=client -o json |
  jq '.metadata.annotations'
```

On a local Kubernetes 1.35.5 cluster, the scheduled Job carried the time.
Reading the same annotation on its Pod returned an empty value. A client
in the Pod retrieved the timestamp from its parent Job using the
`batch.kubernetes.io/job-name` label and permission to get Jobs in the
intake namespace.

The manual Job had the same CronJob owner and carried only
`cronjob.kubernetes.io/instantiate: manual`. Setting
`DEPOSIT_DATE=2026-11-18` in its Pod template before creation selected
November 18. With the date omitted, the trial client stopped with
**Choose a deposit date**.

## Match the result to the delivery

At intake, the archive would upload a ZIP containing one `index.txt` and
save its Boxie artifact ID alongside the sender's expected SHA-256 for
the index file. Each collection, issue date and delivery revision would
have one row. A scheduled run would check the first revision. An archivist
could select a later revision after receiving a replacement. The pilot
fits indexes up to Boxie's 64 MiB limit per archive member.
[Boxie upload limits](../../packages/boxie/docs/execution.md#validate-an-upload)

The client would use its private Boxie credential and an operator-approved
command, `/usr/bin/sha256sum /opt/artifact/index.txt`. In a local Boxie
trial using PostgreSQL and Docker Desktop's `runc`, the sender's original
files contained `issue 18` and `issue 19`, each followed by a newline.
Both delivered copies contained `issue 19` and both jobs exited zero.
Comparing the full hashes gave these verdicts, shown with eight-digit
hash prefixes.

| Issue date | Sender's SHA-256 | Delivered SHA-256 | Intake verdict |
| --- | --- | --- | --- |
| November 18 | `abbab5e5` | `0f923852` | Checksum mismatch · request a replacement |
| November 19 | `0f923852` | `0f923852` | Checksum matched |

Before submission, the client would save the key, such as
`press-index/2026-11-18/r1`, with the exact artifact ID, profile and
command. In the trial, a fresh client repeated the November 18 request and
recovered the result. Each dated job ran once. Substituting the November 19
artifact under the November 18 key returned HTTP 409.

The client would save the compared hashes and verdict in the intake row
before Boxie's result expires seven days after confirmed cleanup. A verdict
requires a successful job and one complete hash for the expected file.
Truncated output, an expired result or an unknown outcome would leave the
row marked **Needs review**.
[Boxie job submission and results](../../packages/boxie/docs/consumer-api.md#submit-a-job-and-retrieve-its-result)

## Compare with hashing in the Kubernetes Job

An ordinary Kubernetes Job can use the same date lookup. In the local
comparison, the retained Pod logs supplied the hashes for both verdicts.
Use the lookup directly where those logs already answer the archivist's
question. To test Boxie, recruit two archive teams that can show a case
where recovering that evidence took operator time. Compare their direct
Job, including its usual logs and saved results, with the proposed
template on a private Linux Boxie host with gVisor. Give both paths the
same sender records and intake table.

Try a delayed mismatch, a manual run with the date omitted and a lost
reply after the runner accepts a check. Require the correct dated
verdict, zero checker launches for the undated run and one recorded
decision for the retry. Count checker launches and time the recovery.
For each team, multiply the minutes saved per recovery by its number of
comparable incidents last quarter. Package the template if both teams
meet the three checks and each would save more time than it takes to set
up Boxie and maintain it for a quarter.
